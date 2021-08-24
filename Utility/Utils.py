from bson import ObjectId
from Utility import Connections

# Funzione che, dato l'id di un gruppo, restituisce il nome associato a quest'ultimo
def getGroupName(group_id):
    return Connections.getGroup().find_one({"_id": ObjectId(group_id)}, {"_id": 0, "name": 1})


# Funzione che, dato un utente, restituisce il suo id
def user_to_group(user):
    res = Connections.getGroup().find({}, {"_id": 1, "User": 1})
    g = []
    for group in res:
        for user_id in group['User']:
            if user == str(user_id):
                g.append(group['_id'])
    return g


def isInList(list, element, firstCon, secondCon):
    for el in list:
        if el[firstCon] == element[secondCon]:
            return True
    return False


def isInListForIntersect(list, element):
    found = 0
    for el in list:
        for temp_el in el:
            if temp_el["_id"] == element["_id"]:
                found += 1
    return found == len(list)


def create_set_intersect(events):
    list_events = []
    for item in events:
        for temp_item in item:
            if isInListForIntersect(events, temp_item):
                if not isInList(list_events, temp_item, "_id", "_id"):
                    list_events.append(temp_item)
    return list_events


def create_set_union(events):
    list_events = []
    for item in events:
        for temp_item in item:
            if not isInList(list_events, temp_item, "_id", "_id"):
                list_events.append(temp_item)
    return list_events


# Funzione che sostituisce all'id del gruppo e del calendario il relativo nome
def manipulateItem(item):
    item["group_id"] = Connections.getGroup().find_one({"_id": ObjectId(item["group_id"])}, {"_id": 0, "name": 1})["name"]
    item["calendar_id"] = Connections.getCal().find_one({"_id": ObjectId(item["calendar_id"])}, {"_id": 0, "type": 1})["type"]
    if item["auth"] == "evento":
        item["condition"] = Connections.getEvent().find_one({"_id": ObjectId(item["condition"])}, {"_id": 0, "title": 1})["title"]
    return item


