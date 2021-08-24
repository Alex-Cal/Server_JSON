from bson import ObjectId
from Utility import Connections

# Funzione che, dato un insieme di autorizzationi, un evento e un tipo di evento, restituisce True se, tra le auth,
# ce n'è una di scrittura che si applica all'evento fornito (o al tipo fornito)
def search_auth_write(auth, event_id, event_type):
    for a in auth:
        # conflitti
        res = Connections.getAuth().find_one({"_id": a[1], "type_auth": "write"})
        if res is None:
            return False
        if res["sign"] == "+":
            if res["auth"] == "any" or \
                    (res["auth"] == "type" and res["condition"] == event_type) or \
                    (res["auth"] == "event" and res["condition"] == event_id):
                return True
        else:
            if (res["auth"] == "type" and res["condition"] != event_type) or \
                    (res["auth"] == "event" and res["condition"] != event_id):
                return True
    return False

# Funzione di utilità che, data una auth il relativo calendario, restituisce gli eventi filtrati in base all'auth
def authorization_filter(id_auth, calendario):
    eventi_good = []
    flag = False
    auth = Connections.getAuth().find_one({"_id": ObjectId(id_auth)},
                         {'calendar_id': 1, 'condition': 1, 'sign': 1, "auth": 1, "type_auth": 1})
    if auth is None:
        return []
    if auth["type_auth"] == "freeBusy":
        eventi = Connections.getEvent().find({'calendar': calendario},
                            {"calendar": 1, "title": 1, "start": 1, "end": 1, "allDay": 1, "color": 1, "type": 1})
        flag = True
    else:
        eventi = Connections.getEvent().find({'calendar': calendario})

    # In caso di freeBusy, non restituire informazioni relative al titolo e ad ulteriori dettagli
    for item in eventi:
        if flag:
            item['title'] = "Slot non disponibile"
        # Controlli in base al tipo di auth (any - tipo - evento)
        if auth["auth"] == "any":
            if auth['sign'] == '+':
                eventi_good.append(item)
            else:
                print("Nessun evento")
                return []
        elif auth["auth"] == "tipo":
            if item['type'] == auth['condition']:
                if auth['sign'] == '+':
                    eventi_good.append(item)
            else:
                if auth['sign'] == '-':
                    if auth["type_auth"] == "write":
                        return []
                    eventi_good.append(item)
        elif auth["auth"] == "evento":
            if item['_id'] == ObjectId(auth['condition']):
                if auth['sign'] == '+':
                    eventi_good.append(item)
            else:
                if auth['sign'] == '-':
                    if auth["type_auth"] == "write":
                        return []
                    eventi_good.append(item)
    return eventi_good

# Funzione che filtra le autorizzazioni in base al tipo type (read, write o freeBusy)
def filter_auth(group_auth, calendar, type):
    # Se esiste solo una auth, restituisci quella, altrimenti, risolvi conflitto
    if group_auth is None:
        return []
    elif len(group_auth["Authorization"]) == 1:
        for a in group_auth["Authorization"]:
            auth = Connections.getAuth().find_one({"_id": a, "type_auth": type})
            if type == "read":
                auth_freeBusy = Connections.getAuth().find_one({"_id": a, "type_auth": "freeBusy"})
                if auth_freeBusy is not None:
                    return group_auth
            if auth is not None:
                return group_auth
        return []
    else:
        temp_list = []
        for a in group_auth["Authorization"]:
            auth = Connections.getAuth().find_one({"_id": a, "type_auth": type})
            if auth is not None:
                temp_list.append(auth["_id"])

            if type == "read":
                auth_freeBusy = Connections.getAuth().find_one({"_id": a, "type_auth": "freeBusy"})
                if auth_freeBusy is not None:
                    temp_list.append(auth_freeBusy["_id"])

        if len(temp_list) == 0:
            return []
        dict = {"Authorization": []}
        for item in temp_list:
            dict["Authorization"].append(item)
        return dict

# Funzione che, dato un insieme di auth, valuta se hanno tutte il segno +, tutte - o misto
def checkSign(auth):
    positive_sign = True
    negative_sign = True
    first_positive_sign = "+"
    first_negative_sign = "-"
    for a in auth:
        auth_ = Connections.getAuth().find_one({"_id": a}, {"_id": 0, "sign": 1})
        if auth_["sign"] != first_positive_sign:
            positive_sign = False
        if auth_["sign"] != first_negative_sign:
            negative_sign = False
    return [positive_sign, negative_sign]