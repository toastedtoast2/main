import json
import time
from appwrite.client import Client
from appwrite.services.databases import Databases

OFFLINE_THRESHOLD = 300  # 5 minutes

def main(context):
    client = Client()
    client.set_endpoint(context.env["APPWRITE_ENDPOINT"])
    client.set_project(context.env["APPWRITE_PROJECT"])
    client.set_key(context.env["APPWRITE_KEY"])

    db = Databases(client)

    DATABASE_ID = context.env["DATABASE_ID"]
    PLAYERS = context.env["PLAYERS_COLLECTION"]
    PARTIES = context.env["PARTY_COLLECTION"]

    now = int(time.time())
    checked = set()

    try:
        parties = db.list_documents(
            database_id=DATABASE_ID,
            collection_id=PARTIES
        )["documents"]
    except Exception as e:
        return context.res.json({"error": str(e)})

    for party in parties:
        # ✅ ONLY check active battles
        if party.get("state") != "battle":
            continue

        try:
            members = json.loads(party.get("member_ids", "[]"))
        except:
            continue

        for member_id in members:
            if member_id in checked:
                continue
            checked.add(member_id)

            try:
                doc = db.get_document(
                    database_id=DATABASE_ID,
                    collection_id=PLAYERS,
                    document_id=member_id
                )

                player = json.loads(doc["playerData"])

                last_active = player.get("last_active", 0)
                last_checked = player.get("last_checked", 0)
                is_offline = player.get("is_offline", False)

                # 🚫 Skip if already offline AND no new activity
                if is_offline and last_active <= last_checked:
                    continue

                # ⏱ Offline check
                if now - last_active > OFFLINE_THRESHOLD:
                    player["is_offline"] = True
                    context.log(f"{member_id} is OFFLINE")

                    # ⚔️ Skip turn if it's theirs
                    if party.get("whose_turn") == member_id:
                        try:
                            turn_order = json.loads(party.get("turn_order", "[]"))
                            if member_id in turn_order:
                                idx = turn_order.index(member_id)
                                next_turn = turn_order[(idx + 1) % len(turn_order)]

                                db.update_document(
                                    database_id=DATABASE_ID,
                                    collection_id=PARTIES,
                                    document_id=party["$id"],
                                    data={"whose_turn": next_turn}
                                )

                                context.log(f"Turn skipped for {member_id}")
                        except Exception as e:
                            context.log(f"Turn error: {e}")

                else:
                    player["is_offline"] = False

                # ✅ mark checked
                player["last_checked"] = now

                # 💾 save player
                db.update_document(
                    database_id=DATABASE_ID,
                    collection_id=PLAYERS,
                    document_id=member_id,
                    data={"playerData": json.dumps(player)}
                )

            except Exception as e:
                context.log(f"Player error ({member_id}): {e}")

    return context.res.json({"status": "done"})