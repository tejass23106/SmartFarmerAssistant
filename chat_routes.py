import json
import sqlite3
import time

from flask import (
    Response, abort, flash, jsonify, redirect,
    render_template, request, session, stream_with_context, url_for
)

from utils import chatbot
from utils.activity import log_activity
from utils.database import get_db
from utils.helpers import role_required
from utils.i18n import translate, valid_lang


RATE_LIMIT, RATE_WINDOW = 15, 600
_hits = {}


def _lang():
    return (
        valid_lang(session.get("lang"))
        or valid_lang(request.cookies.get("lang"))
        or "en"
    )


def register(app):

    @app.route("/chat")
    @role_required("farmer")
    def chat_page():
        uid, cid = session["user_id"], request.args.get("c", type=int)
        conn = get_db()

        try:
            convs = conn.execute(
                "SELECT id, title, updated_at FROM chat_conversations "
                "WHERE user_id=? ORDER BY updated_at DESC, id DESC LIMIT 30",
                (uid,)
            ).fetchall()

            messages, current = [], None

            if cid:
                current = conn.execute(
                    "SELECT * FROM chat_conversations WHERE id=? AND user_id=?",
                    (cid, uid)
                ).fetchone()

                if not current:
                    abort(404)

                messages = conn.execute(
                    "SELECT role, content, created_at FROM chat_messages "
                    "WHERE conversation_id=? ORDER BY id",
                    (cid,)
                ).fetchall()

        finally:
            conn.close()

        return render_template(
            "chat.html",
            convs=convs,
            messages=messages,
            current=current,
            configured=chatbot.is_configured()
        )

    @app.route("/api/chat", methods=["POST"])
    @role_required("farmer")
    def chat_send():
        body = request.get_json(silent=True)

        lang = valid_lang(
            body.get("language") if isinstance(body, dict) else None
        ) or _lang()

        T = lambda key: translate(lang, key)

        if not isinstance(body, dict):
            return jsonify(ok=False, error=T("chat.err_empty")), 400

        message = str(body.get("message", "")).strip()
        cid = body.get("conversation_id")

        if not message:
            return jsonify(ok=False, error=T("chat.err_empty")), 400

        if len(message) > chatbot.MAX_INPUT_CHARS:
            return jsonify(ok=False, error=T("chat.err_long")), 400

        uid, now = session["user_id"], time.time()

        hits = [
            t for t in _hits.get(uid, [])
            if now - t < RATE_WINDOW
        ]

        if len(hits) >= RATE_LIMIT:
            return jsonify(ok=False, error=T("chat.err_rate")), 429

        hits.append(now)
        _hits[uid] = hits

        conn = get_db()

        try:
            history = []

            if cid is not None:
                try:
                    cid = int(cid)
                except (TypeError, ValueError):
                    return jsonify(ok=False, error=T("chat.err_empty")), 400

                conv = conn.execute(
                    "SELECT id FROM chat_conversations WHERE id=? AND user_id=?",
                    (cid, uid)
                ).fetchone()

                if not conv:
                    return jsonify(ok=False, error=T("chat.err_notfound")), 404

                history = [
                    dict(r) for r in conn.execute(
                        "SELECT role, content FROM chat_messages "
                        "WHERE conversation_id=? ORDER BY id",
                        (cid,)
                    )
                ]

            if body.get("stream") is True:
                conn.close()

                def generate():
                    full_reply = ""
                    stream_conn = None

                    try:
                        for chunk in chatbot.stream(history, message, lang):
                            full_reply += chunk

                            yield (
                                "event: token\n"
                                "data: " + json.dumps({"text": chunk}) + "\n\n"
                            )

                        if not full_reply.strip():
                            raise chatbot.ChatError("chat.unavailable")

                        stream_conn = get_db()

                        if cid is None:
                            cur = stream_conn.execute(
                                "INSERT INTO chat_conversations "
                                "(user_id, title, language) VALUES (?,?,?)",
                                (uid, message[:50], lang)
                            )
                            conversation_id = cur.lastrowid

                            log_activity(
                                stream_conn, uid, "farmer",
                                "chat", message[:60]
                            )
                        else:
                            conversation_id = cid

                        stream_conn.execute(
                            "INSERT INTO chat_messages "
                            "(conversation_id, user_id, role, content) "
                            "VALUES (?,?,'user',?)",
                            (conversation_id, uid, message)
                        )

                        stream_conn.execute(
                            "INSERT INTO chat_messages "
                            "(conversation_id, user_id, role, content) "
                            "VALUES (?,?,'assistant',?)",
                            (conversation_id, uid, full_reply)
                        )

                        stream_conn.execute(
                            "UPDATE chat_conversations "
                            "SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                            (conversation_id,)
                        )

                        stream_conn.commit()

                        yield (
                            "event: done\n"
                            "data: " + json.dumps({
                                "conversation_id": conversation_id
                            }) + "\n\n"
                        )

                    except GeneratorExit:
                        raise

                    except chatbot.ChatError as exc:
                        if stream_conn:
                            stream_conn.rollback()

                        yield (
                            "event: error\n"
                            "data: " + json.dumps({
                                "error": T(exc.key)
                            }) + "\n\n"
                        )

                    except sqlite3.Error:
                        if stream_conn:
                            stream_conn.rollback()

                        yield (
                            "event: error\n"
                            "data: " + json.dumps({
                                "error": T("err.database")
                            }) + "\n\n"
                        )

                    except Exception:
                        if stream_conn:
                            stream_conn.rollback()

                        yield (
                            "event: error\n"
                            "data: " + json.dumps({
                                "error": T("chat.unavailable")
                            }) + "\n\n"
                        )

                    finally:
                        if stream_conn:
                            stream_conn.close()

                return Response(
                    stream_with_context(generate()),
                    content_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no"
                    }
                )

            try:
                reply = chatbot.ask(history, message, lang)

            except chatbot.ChatError as exc:
                return jsonify(ok=False, error=T(exc.key)), (
                    503 if exc.key == "chat.not_configured" else 502
                )

            if cid is None:
                cur = conn.execute(
                    "INSERT INTO chat_conversations "
                    "(user_id, title, language) VALUES (?,?,?)",
                    (uid, message[:50], lang)
                )
                cid = cur.lastrowid

                log_activity(
                    conn, uid, "farmer", "chat", message[:60]
                )

            conn.execute(
                "INSERT INTO chat_messages "
                "(conversation_id, user_id, role, content) "
                "VALUES (?,?,'user',?)",
                (cid, uid, message)
            )

            conn.execute(
                "INSERT INTO chat_messages "
                "(conversation_id, user_id, role, content) "
                "VALUES (?,?,'assistant',?)",
                (cid, uid, reply)
            )

            conn.execute(
                "UPDATE chat_conversations "
                "SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (cid,)
            )

            conn.commit()

        except sqlite3.Error:
            conn.rollback()
            return jsonify(ok=False, error=T("err.database")), 500

        finally:
            conn.close()

        return jsonify(
            ok=True,
            reply=reply,
            conversation_id=cid
        )

    @app.route("/chat/<int:conv_id>/delete", methods=["POST"])
    @role_required("farmer")
    def chat_delete(conv_id):
        conn = get_db()

        try:
            cur = conn.execute(
                "DELETE FROM chat_conversations WHERE id=? AND user_id=?",
                (conv_id, session["user_id"])
            )

            conn.commit()

            flash(
                "chat.deleted" if cur.rowcount else "chat.err_notfound",
                "success" if cur.rowcount else "danger"
            )

        except sqlite3.Error:
            conn.rollback()
            flash("err.database", "danger")

        finally:
            conn.close()

        return redirect(url_for("chat_page"))