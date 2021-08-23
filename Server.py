import os
import time
import json
import re
from datetime import datetime
from io import BytesIO

import networkx as nx
from bottle import run, request, post, get, app, response, route
from bottle_cors_plugin import cors_plugin
import pymongo
import bottle
from bson import json_util, ObjectId

# Connection to MongoDB
from matplotlib import pyplot as plt

myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["CalendarDB"]
Cal = mydb["Calendar"]
Event = mydb["Events"]
Precondition = mydb["Temporal Pre-Condition"]
Admin_Auth = mydb["Admin_Auth"]
Auth = mydb["Authorization"]
User = mydb["User"]
Group = mydb["Group"]
Hier = mydb["Hier"]


# N.B. Se ci sono due auth, con stesso segno e stesso tipo, bisogna prendere la più generale/specifica ==== controllare
class EnableCors(object):
    name = 'enable_cors'
    api = 2

    def apply(self, fn, context):
        def _enable_cors(*args, **kwargs):
            # set CORS headers
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
            response.headers[
                'Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'

            if bottle.request.method != 'OPTIONS':
                # actual request; reply with the actual response
                return fn(*args, **kwargs)

        return _enable_cors


app = bottle.app()


@app.route('/cors', method=['OPTIONS', 'POST', 'GET'])
def lvambience():
    response.headers['Content-type'] = 'application/json'
    return '[1]'


def get_all_types(request):
    commas = []
    types = []
    for item in re.finditer(',', request):
        commas.append(item.start())

    if len(commas) == 0:
        return request
    types.append(request[0:commas[0]])
    # add check if - greater than 1
    for i in range(0, len(commas) - 1):
        types.append(request[commas[i] + 1: commas[i + 1]])
    types.append(request[commas[len(commas) - 1] + 1:len(request)])
    return types


@post('/all_type_event')
def all_type():
    query = get_query_new(request.body.read().decode('utf-8'))
    res = Event.find({"creator": query["id"]}, {"type": 1})
    lista_event = set()
    for item in res:
        lista_event.add(item["type"])
    return json_util.dumps(lista_event)


@post("/calendar_event")
def cal_event():
    query = get_query_new(request.body.read().decode('utf-8'))
    res = Event.find({"calendar": query['calendar']}, {"_id": 1, "title": 1})
    lista_event = []
    for item in res:
        lista_event.append(item)
    return json_util.dumps(lista_event)


# modify a given event title

# Se sei un delegato del calendario X, bisogna controllare l'evento che vuoi modificare
# Se l'evento ha come creator l'owner del calendario === fermo, non fai nulla --- present=False
# Se l'evento ha come creator un delegato ADMIN e tu sei un delegato ROOT --- present = True e lo modifichi
# Se sei un delegato ADMIN e l'evento è stato creato da te, allora puoi modificarlo --- present = TRUE
# Se sei delegato ROOT e l'evento è creato da qualsiasi persona, all'infuori dell'owner --- Present = True

@post('/mod_event')
def update_events():
    query = get_query_new(request.body.read().decode('utf-8'))
    query['_id'] = ObjectId(query['_id'])
    myquery = {"_id": (query['_id'])}
    eventToUpdate = Event.find_one(myquery)

    present_delegate = False
    present_user = False

    existAuth = Admin_Auth.find_one({"user_id": query["username"], "calendar_id": query["calendar"]})
    isOwner = Cal.find_one({"_id": ObjectId(query['calendar']), "owner": query["username"]})
    if isOwner is not None:
        query["creator"] = query["username"]
        query.pop('username')
        Event.delete_one(myquery)
        Event.insert_one(query)
        return "Modifica completata con successo"
    elif existAuth is not None:
        checkAminDel = Admin_Auth.find_one({"user_id": eventToUpdate["creator"], "calendar_id": query["calendar"]})
        if checkAminDel is not None:
            if (checkAminDel["level"] == "DELEGATO_ADMIN" and existAuth["level"] == "DELEGATO_ROOT") or \
                    (eventToUpdate["creator"] == query["username"]) or \
                    (existAuth["level"] == "DELEGATO_ADMIN" and eventToUpdate["creator"] == existAuth["user_id"]):
                present_delegate = True
    else:
        event_user_can_update = eventUserCanWrite(query["username"], query["calendar"])
        for item in event_user_can_update:
            if item["_id"] == query["_id"]:
                present_user = True

    if present_delegate:
        query["creator"] = query["username"]
        query.pop('username')
        Event.delete_one(myquery)
        canUpdDateTime = canADelegateAccessTimeslot(query["creator"], query["calendar"], query["start"], query["end"])
        if (query["start"] == eventToUpdate["start"] and query["end"] == eventToUpdate["end"]) or canUpdDateTime:
            Event.insert_one(query)
            return "Evento modificato"
        elif not canUpdDateTime:
            query["start"] = eventToUpdate["start"]
            query["end"] = eventToUpdate["end"]
            Event.insert_one(query)
            return "Errore nella modifica, timeslot invariato"
    elif present_user:
        Event.delete_one(myquery)
        query.pop('username')
        query["start"] = eventToUpdate["start"]
        query["end"] = eventToUpdate["end"]
        Event.insert_one(query)
        return "Modifica completata con successo (timeslot invariato)"
    return "Errore nella modifica"


def canADelegateAccessTimeslot(user_id, calendar_id, start_time_to_insert, end_time_to_insert):
    admin_pre = Admin_Auth.find_one({"user_id": user_id, "calendar_id": calendar_id})
    if admin_pre is not None:
        start = datetime.fromtimestamp(int(start_time_to_insert))
        end = datetime.fromtimestamp(int(end_time_to_insert))
        if admin_pre["repetition"] == "false":
            timeslot = admin_pre["start"] + "-" + admin_pre["end"]
            [start_date, start_hour, end_date, end_hour] = string_not_repetition(timeslot)

            if (datetime.date(start)) >= start_date and (datetime.date(end)) <= end_date:
                if datetime.time(start) >= start_hour and datetime.time(end) <= end_hour:
                    return True
            return False
        else:
            timeslot = admin_pre["startDay"] + "." + admin_pre["startHour"] + ":" + admin_pre["startMin"] + "-" + \
                       admin_pre["endDay"] + "." + admin_pre["endHour"] + ":" + admin_pre["endMin"]
            [start_day, start_hour, end_day, end_hour] = string_repetition(timeslot)

            start_hour_adm = datetime.strptime(start_hour, "%H:%M").time()
            end_hour_adm = datetime.strptime(end_hour, "%H:%M").time()
            if int(datetime.weekday(start)) >= int(start_day) and int(datetime.weekday(end)) <= int(end_day):
                if datetime.time(start) >= start_hour_adm and datetime.time(end) <= end_hour_adm:
                    return True
        return False
    return False


# N.B. gestire auth più specifica e conflitto e delegato
def search_auth_write(auth, event_id, event_type):
    for a in auth:
        # conflitti
        res = Auth.find_one({"_id": a[1], "type_auth": "write"})
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


@get('/image')
def video_image():
    user_id = request.query.user
    return bottle.static_file((user_id + ".jpg"), root="", mimetype='image/jpg')


def getGroupName(group_id):
    return Group.find_one({"_id": ObjectId(group_id)}, {"_id": 0, "name": 1})


@post("/user_cal")
def user_cal():
    query = get_query_new(request.body.read().decode('utf-8'))
    list_cal = []
    list_calendar = set()
    list_group = []
    groups_hier = []
    res = Cal.find({"owner": query['id']}, {"type": 1, "xor": 1, "_id": 1})
    # calendari di cui l'utente è proprietario
    for item in res:
        temp = {
            "id": str(item["_id"]),
            "type": item["type"],
            "xor": item["xor"]
        }
        list_cal.append(temp)

    # calendari per cui l'utente è delegato
    res = Cal.find({}, {"Admin_auth": 1, "_id": 1, "type": 1, "xor": 1})
    for item in res:
        for auth in item["Admin_auth"]:
            admin_auth = Admin_Auth.find_one({"_id": ObjectId(auth)})
            if query["id"] == admin_auth["user_id"]:
                temp = {
                    "id": str(item["_id"]),
                    "type": item["type"],
                    "xor": item["xor"]
                }
                list_cal.append(temp)

    # calendari su cui l'utente ha autorizzazioni di visibilità
    ris = Group.find({}, {"_id": 1, "User": 1})
    for item in ris:
        for user in item['User']:
            if user == ObjectId(query['id']):
                list_group.append(str(item['_id']))

    # calendari a cui l'utente non ha accesso diretto, ma eredita l'accesso dalla gerarchia
    for group in list_group:
        res = Group.find({"_id": ObjectId(group)}, {"creator": 1, "name": 1})
        for g in res:
            G = getG(g["creator"])
            n = getGroupName(group)["name"]
            while n != "ANY":
                for node in G.successors(n):
                    n = node
                    group_find = Group.find_one({"name": node, "creator": g["creator"]}, {"_id": 1})
                    if group_find is not None:
                        groups_hier.append(str(group_find["_id"]))

    complete_groups = groups_hier + list_group

    for item in complete_groups:
        result = Auth.find({"group_id": item}, {"calendar_id": 1})
        for cal in result:
            list_calendar.add(cal['calendar_id'])

    for cal in list_calendar:
        res = Cal.find_one({"_id": ObjectId(cal)}, {"type": 1, "_id": 1, "xor": 1})
        temp = {
            "id": str(res["_id"]),
            "type": res["type"],
            "xor": res["xor"]
        }
        if not isInList(list_cal, temp, "id", "id"):
            list_cal.append(temp)

    return json_util.dumps(list_cal)


# delete a specific event parametri saranno l'id dell'evento da cancellare ed il calendario di riferimento
@post('/delete_event')
def delete_event():
    query = get_query_new(request.body.read().decode('utf-8'))
    print(query)
    myquery = {"_id": ObjectId(query['_id'])}
    res = Event.find_one(myquery, {"calendar": 1})
    ris = Event.delete_one(myquery)
    new_query = {"_id": ObjectId(res['calendar'])}
    Cal.update_one(new_query, {"$pull": {'Events': ObjectId(query['_id'])}})
    if ris.deleted_count != 1:
        return "Errore nella cancellazione"
    return "Cancellazione completata con successo"


def create_query(list_param):
    query = {}
    for i in range(0, len(list_param)):
        query[list_param[i][0]] = list_param[i][1]
    return query


def get_query_new(r):
    request = r[1:len(r) - 1]
    pair = []
    point_list = []
    comma_list = []
    for item in re.finditer(',', request):
        comma_list.append(item.start())

    for item in re.finditer(':', request):
        point_list.append(item.start())

    if len(comma_list) == 0:
        pair.append(((request[1:point_list[0] - 1]), request[point_list[0] + 2:len(request) - 1]))
        return create_query(pair)
    pair.append(((request[1:point_list[0] - 1]), request[point_list[0] + 2:comma_list[0] - 1]))
    for i in range(0, len(comma_list) - 1):
        pair.append(
            (request[comma_list[i] + 2:point_list[i + 1] - 1], request[point_list[i + 1] + 2:comma_list[i + 1] - 1]))
    pair.append((request[comma_list[len(comma_list) - 1] + 2:point_list[len(comma_list)] - 1],
                 request[point_list[len(comma_list)] + 2:len(request) - 1]))
    return create_query(pair)


def isConflict(start_a, end_a, start_b, end_b):
    start = datetime.fromtimestamp(int(start_a))
    end = datetime.fromtimestamp(int(end_a))

    start_c = datetime.fromtimestamp(int(start_b))
    end_c = datetime.fromtimestamp(int(end_b))

    if datetime.date(start) >= datetime.date(start_c) and datetime.date(end) <= datetime.date(end_c):
        if datetime.time(start) >= datetime.time(start_c) and datetime.time(end) <= datetime.time(end_c):
            return True
    return False


def isThereAConflict(event_calendar, start, end, creator):
    owner = Cal.find_one({"_id": ObjectId(event_calendar)}, {"owner": 1, "_id": 0})
    clashed_event = {}
    if owner is not None:
        calendars = Cal.find({"owner": owner["owner"]})
        for calendar in calendars:
            for event in calendar["Events"]:
                event_to_check_with = Event.find_one({"_id": event})
                if event_to_check_with is not None:
                    if isConflict(start, end, event_to_check_with["start"], event_to_check_with["end"]):
                        clashed_event = event_to_check_with
    if len(clashed_event) != 0:

        if clashed_event["calendar"] == event_calendar:
            print("Clash sullo stesso calendario", event_calendar)
            if owner["owner"] == clashed_event["creator"]:
                return False
            delegate_new_event = Admin_Auth.find_one({"user_id": creator}, {"level": 1})
            delegate_old_event = Admin_Auth.find_one({"user_id": clashed_event["creator"]}, {"level": 1})
            if delegate_old_event["level"] == delegate_new_event["level"] or \
                    (delegate_new_event["level"] == "DELEGATO_ROOT" and delegate_old_event["level"] == "DELEGATO_ADMIN"):
                return True
            if delegate_old_event["level"] == "DELEGATO_ROOT" and delegate_new_event["level"] == "DELEGATO_ADMIN":
                return False

        else:
            complete_event_calendar = Cal.find_one({"_id": ObjectId(event_calendar)})
            complete_clash_event_calendar = Cal.find_one({"_id": ObjectId(clashed_event["calendar"])})
            print("Clash su calendari diversi", event_calendar, clashed_event["calendar"])
            if (complete_event_calendar["xor"] == "true" and complete_clash_event_calendar == "false") or \
                    (complete_event_calendar["xor"] == "false" and complete_clash_event_calendar == "false"):
                return True
            if complete_event_calendar["xor"] == "true" and complete_clash_event_calendar == "true":
                return "EX"
            if complete_event_calendar["xor"] == "false" and complete_clash_event_calendar == "true":
                return False
    return True

@post('/insert_event')
def insert_event():
    # controllare se si tratta dell'owner o di un delegato; serve lo username dell'utente che vuole fare l'operazione
    query = get_query_new(request.body.read().decode('utf-8'))
    # print(query)
    isOwner = Cal.find_one({"_id": ObjectId(query['calendar']), "owner": query["creator"]})
    if isOwner is not None:
        Event.insert_one(query)
        myquery = {'_id': ObjectId(query['calendar'])}
        res = Event.find({}, {'_id'}).sort('_id', -1).limit(1)
        newvalues = {"$addToSet": {'Events': ObjectId(res[0]['_id'])}}
        Cal.update_one(myquery, newvalues)
        return "Inserimento completato con successo (owner del calendario)"

    existAuth = Admin_Auth.find_one({"user_id": query["creator"], "calendar_id": query["calendar"]})
    if existAuth is not None:
        isAble = canADelegateAccessTimeslot(query["creator"], query["calendar"], query["start"], query["end"])
        if isAble:
            canSet = isThereAConflict(query["calendar"], query["start"], query["end"], query["creator"])
            if canSet:
                Event.insert_one(query)
                myquery = {'_id': ObjectId(query['calendar'])}
                res = Event.find({}, {'_id'}).sort('_id', -1).limit(1)
                newvalues = {"$addToSet": {'Events': ObjectId(res[0]['_id'])}}
                Cal.update_one(myquery, newvalues)
                return "Inserimento completato con successo (delegato e giusto intervallo)"
            elif canSet == "X":
                #setta il colore a strano
                Event.insert_one(query)
                myquery = {'_id': ObjectId(query['calendar'])}
                res = Event.find({}, {'_id'}).sort('_id', -1).limit(1)
                newvalues = {"$addToSet": {'Events': ObjectId(res[0]['_id'])}}
                Cal.update_one(myquery, newvalues)
                return "Inserimento in due calendari esclusivi; inserimento permesso, con riserva di decisione per l'owner"
            else:
                return "Presente un clash, errore nell'inserimento"
        else:
            return "Errore nell'inserimento, timeslot a te non disponibile"
    return "Errore nell'inserimento"


# curl --data "type=School&owner=Alex" http://0.0.0.0:12345/insert_cal
@post('/insert_cal')
def insert_cal():
    query = get_query_new(request.body.read().decode('utf-8'))
    query2 = {"Events": [], "Precondition": [], "Admin_auth": [], "Authorization": []}
    new_dict = {**query, **query2}
    Cal.insert_one(new_dict)
    return "Inserimento del calendario avvenuto con successo"


@post('/list_cal_owner')
def cal_owner():
    query = get_query_new(request.body.read().decode('utf-8'))
    list_cal = []
    res = Cal.find({"owner": query['id']}, {"type": 1, "_id": 1})
    for item in res:
        list_cal.append(item)
    return json_util.dumps(list_cal)


# curl --data "name=Bob&Surname=Red" http://0.0.0.0:12345/insert_user
@post('/insert_user')
def insert_user():
    query = get_query_new(request.body.read().decode('utf-8'))
    node = [
        {"node_value": "ANY"},
    ]
    query["_id"] = ObjectId(query["_id"])
    query2 = {"Group": [], "Precondition": [], "Admin_auth": [], "Authorization": []}
    new_dict = {**query, **query2}
    if User.find_one({"_id": query['_id']}) is None:
        User.insert_one(new_dict)
        query_id = {"owner": str(query["_id"]), "Hier": []}
        G = nx.DiGraph()
        G.add_node("ANY")
        save_image(G, str(query["_id"]))
        Hier.insert_one(query_id)
        update = {"$addToSet": {'Hier': {"node": "ANY", "belongsto": ""}}}
        query = {'owner': str(query["_id"])}
        Hier.update_one(query, update)


def save_image(G, id):
    pos = nx.spring_layout(G, seed=100)
    nx.draw(G, pos, with_labels=True, node_size=1500, font_size=10)
    plt.savefig(id + ".jpg")
    plt.close()


@post("/add_group_hier")
def group_hier():
    query = get_query_new(request.body.read().decode('utf-8'))
    id = query["id"]
    update = {"$addToSet": {'Hier': {"node": query["son"], "belongsto": query["dad"]}}}
    query = {'owner': query["id"]}
    Hier.update_one(query, update)
    G = getG(id)
    save_image(G, id)


def getG(id):
    query = {'owner': id}
    hier = Hier.find_one(query, {"Hier": 1, "_id": 0})
    G = nx.DiGraph()
    for a in hier["Hier"]:
        if a["belongsto"] != "":
            G.add_edge(a["node"], a["belongsto"])
    return G


@post('/insert_group')
def insert_group():
    query = get_query_new(request.body.read().decode('utf-8'))
    query2 = {"User": [], "Precondition": [], "Authorization": []}
    new_dict = {**query, **query2}
    if Group.find_one({"name": query["name"], "creator": query["creator"]}) is None:
        Group.insert_one(new_dict)
        return "Gruppo inserito con successo"
    return "Impossibile inserire il gruppo"


@post("/list_us")
def list_us():
    res = User.find({}, {"name": 1, "_id": 0})
    return json_util.dumps(res)


# curl --data "id=1&subject=Carol&calendar=School&type_event=Lezione&prop=null&type_auth=read&sign=+" http://0.0.0.0:12345/ins_auth
@post("/ins_auth")
def insert_auth():
    query = get_query_new(request.body.read().decode('utf-8'))
    print(query)
    myquery = {'_id': ObjectId(query['calendar_id'])}
    myquery2 = {'_id': ObjectId(query['group_id'])}
    isDelegate = Admin_Auth.find_one({"user_id": query["creator"], "calendar_id": query["calendar_id"]})
    if isDelegate is not None:
        if isDelegate["level"] == "DELEGATO_ADMIN" and query["type_auth"] == "write":
            return "Impossibile inserire l'autorizzazione"

    Auth.insert_one(query)
    res = Auth.find({}, {'_id'}).sort('_id', -1).limit(1)
    newvalues = {"$addToSet": {'Authorization': ObjectId(res[0]['_id'])}}
    if User.find_one(myquery2) is None:
        Group.update_one(myquery2, newvalues)
    else:
        User.update_one(myquery2, newvalues)
    Cal.update_one(myquery, newvalues)
    return "Autorizzazione inserita con successo"


@post('/calendar_delegate')
def calendar_delegate():
    query = get_query_new(request.body.read().decode('utf-8'))
    res = Admin_Auth.find({"user_id": query["id"]}, {"calendar_id": 1})
    calend = []
    for calendar in res:
        cal = Cal.find_one({"_id": ObjectId(calendar["calendar_id"])}, {"_id": 1, "type": 1})
        calend.append(cal)
    return json_util.dumps(calend)


@post('/precondition')
def insert_precondition():
    query = get_query_new(request.body.read().decode('utf-8'))
    myquery = {'_id': ObjectId(query['calendar_id'])}
    myquery1 = {'_id': ObjectId(query['group_id'])}
    if query['repetition'] == 'true':
        timeslot = query['startDay'] + "." + query['startHour'] + ":" + query['startMin'] + "-" + query[
            'endDay'] + "." + query['endHour'] + ":" + query['endMin']
        query.pop('startDay')
        query.pop('startHour')
        query.pop('startMin')
        query.pop('endDay')
        query.pop('endHour')
        query.pop('endMin')
    else:
        timeslot = query['start'] + "-" + query['end']
        query.pop('start')
        query.pop('end')
    newquery = {"timeslot": timeslot}
    new_dict = {**query, **newquery}
    Precondition.insert_one(new_dict)
    res = Precondition.find({}, {'_id'}).sort('_id', -1).limit(1)
    newvalues = {"$addToSet": {'Precondition': ObjectId(res[0]['_id'])}}

    if (User.find_one(myquery1)) is None:
        Group.update_one(myquery1, newvalues)
    else:
        User.update_one(myquery1, newvalues)
    Cal.update_one(myquery, newvalues)
    return "Precondizione inserita"


@post('/auth_admin')
def insert_admin_auth():
    query = get_query_new(request.body.read().decode('utf-8'))
    existUser = User.find_one({"username": query["username"]})
    if existUser is None:
        return "Utente inesistente"
    if existUser["_id"] == ObjectId(query["creator"]):
        return "Impossibile delegare l'owner"
    print(query)

    existAuth = Admin_Auth.find_one({"user_id": str(existUser["_id"]), "calendar_id": query["calendar_id"]})
    if existAuth is not None:
        return "È già presente una autorizzazione per questo utente, su questo calendario"

    query.pop('username')
    user_id = {"user_id": str(existUser["_id"])}
    to_insert = {**query, **user_id}
    Admin_Auth.insert_one(to_insert)

    res = Admin_Auth.find({}, {'_id'}).sort('_id', -1).limit(1)
    newvalues = {"$addToSet": {'Admin_auth': ObjectId(res[0]['_id'])}}
    myquery = {'_id': ObjectId(query['calendar_id'])}
    myquery1 = {'_id': existUser["_id"]}
    User.update_one(myquery1, newvalues)
    Cal.update_one(myquery, newvalues)
    return "Autorizzazione inserita con successo"


@post('/list_created_group')
def list_group():
    query = get_query_new(request.body.read().decode('utf-8'))
    lista_group_id = []
    res = Group.find({"creator": query["id"]}, {"name": 1, "_id": 1})
    if res is None:
        return []
    for item in res:
        lista_group_id.append(item)
    return json_util.dumps(lista_group_id)


@post("/insert_user_group")
def insert_user_group():
    query = get_query_new(request.body.read().decode('utf-8'))
    res = Cal.find_one({"owner": query["id"]})
    if res is None:
        return "Operazione non autorizzata"
    else:
        res = User.find_one({"username": query["user"]}, {"_id": 1})
        if res is None:
            return "Utente inesistente"
        else:
            if (Group.find_one({'_id': ObjectId(query['group'])})) is not None:
                newvalues = {"$addToSet": {'User': res['_id']}}
                Group.update_one({'_id': ObjectId(query['group'])}, newvalues)
            else:
                return "Gruppo inesistente"
    return "Utente inserito correttamente nel gruppo"


# @post("/group_id")
# def group_id():
#     query = get_query_new(request.body.read().decode('utf-8'))
#     lista = []
#     res = Group.find({"name": query['name']}, {"_id": 1, "name": 1})
#     for item in res:
#         lista.append(str(item["_id"]) + "-" + item["name"])
#     return lista


def string_repetition(timeslot):
    minus_position = 0
    for item in re.finditer('-', timeslot):
        minus_position = item.start()
    start_day = timeslot[0:1]
    start_hour = timeslot[2:minus_position]
    end_day = timeslot[minus_position + 1:minus_position + 2]
    end_hour = timeslot[minus_position + 3:len(timeslot)]
    return [start_day, start_hour, end_day, end_hour]


def string_not_repetition(timeslot):
    minus_position = 0
    for item in re.finditer('-', timeslot):
        minus_position = item.start()
    start_date = timeslot[0:minus_position]
    end_date = timeslot[minus_position + 1:len(timeslot)]
    start_date_pre = datetime.fromtimestamp(int(start_date))
    end_date_pre = datetime.fromtimestamp(int(end_date))

    start_date_param = datetime.date(start_date_pre)
    end_date_param = datetime.date(end_date_pre)
    start_hour_param = datetime.time(start_date_pre)
    end_hour_param = datetime.time(end_date_pre)
    return [start_date_param, start_hour_param, end_date_param, end_hour_param]


def evaluate_not_rep_admin(timeslot, events):
    [start_date, start_hour, end_date, end_hour] = string_not_repetition(timeslot)
    good_event = []
    for item in events:
        start = datetime.fromtimestamp(int(item["start"]))
        end = datetime.fromtimestamp(int(item["end"]))
        if (datetime.date(start)) >= start_date and (datetime.date(end)) <= end_date:
            if datetime.time(start) >= start_hour and datetime.time(end) <= end_hour:
                good_event.append(item)
    return good_event


def evaluate_rep_admin(timeslot, events):
    [start_day, start_hour, end_day, end_hour] = string_repetition(timeslot)
    good_event = []
    for item in events:
        start = datetime.fromtimestamp(int(item["start"]))
        end = datetime.fromtimestamp(int(item["end"]))
        start_hour_adm = datetime.strptime(start_hour, "%H:%M").time()
        end_hour_adm = datetime.strptime(end_hour, "%H:%M").time()
        if int(datetime.weekday(start)) >= int(start_day) and int(datetime.weekday(end)) <= int(end_day):
            if datetime.time(start) >= start_hour_adm and datetime.time(end) <= end_hour_adm:
                good_event.append(item)
    return good_event


# -------------------------------------------------------------------------------------------------------
def evaluate_not_rep(timeslot, eventi):
    [start_date, start_hour, end_date, end_hour] = string_not_repetition(timeslot)
    good_event = []
    # print(eventi)
    for item in eventi:
        start = datetime.fromtimestamp(int(item["start"]))
        end = datetime.fromtimestamp(int(item["end"]))
        if datetime.date(start) > end_date or datetime.date(end) < start_date:
            good_event.append(item)
        elif datetime.time(start) > end_hour or datetime.time(end) < start_hour:
            good_event.append(item)
    return good_event


def evaluate_rep(timeslot, eventi):
    [start_day, start_hour, end_day, end_hour] = string_repetition(timeslot)
    good_event = []
    for item in eventi:
        start = datetime.fromtimestamp(int(item["start"]))
        end = datetime.fromtimestamp(int(item["end"]))
        start_hour_pre = datetime.strptime(start_hour, "%H:%M").time()
        end_hour_pre = datetime.strptime(end_hour, "%H:%M").time()

        if int(datetime.weekday(start)) > int(end_day) or int(datetime.weekday(end)) < int(start_day):
            good_event.append(item)
        elif datetime.time(start) > end_hour_pre or datetime.time(end) < start_hour_pre:
            good_event.append(item)
    return good_event


def authorization_filter(id_auth, calendario):
    eventi_good = []
    flag = False
    auth = Auth.find_one({"_id": ObjectId(id_auth)},
                         {'calendar_id': 1, 'condition': 1, 'sign': 1, "auth": 1, "type_auth": 1})
    if auth is None:
        return []
    if auth["type_auth"] == "freeBusy":
        eventi = Event.find({'calendar': calendario},
                            {"calendar": 1, "title": 1, "start": 1, "end": 1, "allDay": 1, "color": 1, "type": 1})
        flag = True
    else:
        eventi = Event.find({'calendar': calendario})

    for item in eventi:
        if flag:
            item['title'] = "Slot non disponibile"

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


@post("/events_delegate")
def eventsCanView():
    query = get_query_new(request.body.read().decode('utf-8'))
    delegate_events = eventsADelegateCanRead(query["id"], query["calendar_id"])
    if len(delegate_events) != 0:
        return json_util.dumps(delegate_events)


@post("/types_delegate")
def eventsCanView():
    query = get_query_new(request.body.read().decode('utf-8'))
    delegate_events = eventsADelegateCanRead(query["id"], query["calendar_id"])
    types = set()
    if len(delegate_events) != 0:
        for item in delegate_events:
            types.add(item["type"])
        return json_util.dumps(types)


@post("/groups_delegate")
def groups_delegate():
    query = get_query_new(request.body.read().decode('utf-8'))
    res = Auth.find({"calendar_id": query["calendar_id"]}, {"group_id": 1, "_id": 0})
    g = []
    for groups in res:
        group = Group.find_one({"_id": ObjectId(groups["group_id"])}, {"_id": 1, "name": 1})
        if not isInList(g, group, "_id", "_id"):
            g.append(group)
    print(g)
    return json_util.dumps(g)


def precond(pre, eventi, calendar):
    for i in pre:
        timeslot = Precondition.find_one({"_id": i, "calendar_id": calendar})
        if timeslot is None:
            return eventi
        if timeslot["repetition"] == "true":
            return evaluate_rep(timeslot['timeslot'], eventi)
        else:
            return evaluate_not_rep(timeslot['timeslot'], eventi)
    return eventi


def auth_adm(auth, query):
    for i in auth:
        timeslot = Admin_Auth.find_one({"_id": i},
                                       {"timeslot": 1, "_id": 0, "type_time": 1})
        if timeslot["type_time"] == "repetition":
            return evaluate_rep_admin(timeslot['timeslot'], query['calendar'])

        else:
            return evaluate_not_rep_admin(timeslot['timeslot'], query['calendar'])


def user_to_group(user):
    res = Group.find({}, {"_id": 1, "User": 1})
    g = []
    for group in res:
        for user_id in group['User']:
            if user == str(user_id):
                g.append(group['_id'])
    return g


def solve_conflict(group_auth, calendar, type):
    # Se esiste solo una auth, restituisci quella, altrimenti, risolvi conflitto
    if group_auth is None:
        return []
    elif len(group_auth["Authorization"]) == 1:
        for a in group_auth["Authorization"]:
            auth = Auth.find_one({"_id": a, "type_auth": type})
            if type == "read":
                auth_freeBusy = Auth.find_one({"_id": a, "type_auth": "freeBusy"})
                if auth_freeBusy is not None:
                    return group_auth
            if auth is not None:
                return group_auth

        return []
    else:
        temp_list = []
        for a in group_auth["Authorization"]:
            auth = Auth.find_one({"_id": a, "type_auth": type})
            if auth is not None:
                temp_list.append(auth["_id"])

            if type == "read":
                auth_freeBusy = Auth.find_one({"_id": a, "type_auth": "freeBusy"})
                if auth_freeBusy is not None:
                    temp_list.append(auth_freeBusy["_id"])

        if len(temp_list) == 0:
            return []
        dict = {"Authorization": []}
        for item in temp_list:
            dict["Authorization"].append(item)
        return dict


def getVisibileEventsWithHier(user, calendar, function_scope):
    authorization_type_to_find = "write"
    if function_scope == "show":
        authorization_type_to_find = "read"
    # otteniamo proprietario del calendario e la sua relativa gerarchia
    owner_Cal = Cal.find_one({"_id": ObjectId(calendar)}, {"_id": 0, "owner": 1})
    G = getG(owner_Cal["owner"])
    # otteniamo la lista dei gruppi a cui l'utente appartiene
    g_id = (user_to_group(user))
    group_name = []
    for group in g_id:
        group_name.append(Group.find_one({"_id": group}, {"_id": 0, "name": 1}))
    groups_auth = []
    no_event = False
    for group in group_name:
        n = group["name"]
        # ciclichiamo sul grafo alla ricerca di altre autorizzazioni, che verranno ereditate, partendo dal gruppo più
        # vicino all'utente
        # salviamo le autorizzazioni del gruppo più vicino all'utente e risolviamo conflitti, se ne esistono
        auth_for_group = Group.find_one({"name": n, "creator": owner_Cal["owner"]},
                                        {"_id": 0, "Authorization": 1})
        groups_auth.append((solve_conflict(auth_for_group, calendar, authorization_type_to_find)))
        while n != "ANY":
            for node in G.successors(n):
                n = node
                # salviamo le autorizzazioni dei gruppi più alti in gerarchia e risolviamo conflitti, se ne esistono
                auth_for_group = Group.find_one({"name": node, "creator": owner_Cal["owner"]},
                                                {"_id": 0, "Authorization": 1})
                groups_auth.append((solve_conflict(auth_for_group, calendar, authorization_type_to_find)))
        no_event = True

    for item in groups_auth:
        if len(item) != 0:
            no_event = False
    # Se non esistono eventi visualizzabili, ritorna lista vuota
    if no_event:
        return []

    events_evaluated = []
    # analizza tutti i segni delle autorizzazioni, per capire se sono concordi o discordi
    # print(groups_auth)
    for auth in groups_auth:
        if len(auth) != 0:
            events_group = []
            [positive_sign, negative_sign] = checkSign(auth["Authorization"])
            for a in (auth["Authorization"]):
                events_group.append(authorization_filter(a, calendar))
            # print(events_group)
            # if same sign = union; else, intersection
            if positive_sign:
                events_evaluated.append((create_set_union(events_group), "+"))
            else:
                events_evaluated.append((create_set_intersect(events_group), "-"))

    result = []
    for i in range(0, len(events_evaluated) - 1, 1):
        list_temp = [events_evaluated[i][0], events_evaluated[i + 1][0]]
        if events_evaluated[i][1] == "+":
            result = create_set_union(list_temp)
        else:
            result = create_set_intersect(list_temp)
        return result

    return events_evaluated[0][0]

    # Recuperiamo tutti i gruppi fino ad ANY, da G
    # Ottenuti tutti i gruppi, è necessario recuperare tutte le autorizzazioni associate a ogni gruppo
    # Salviamo, quindi, tutti gli eventi visibili, autorizzazioni per autorizzazione e, volta per volta, a seconda del tipo/segno uniamo o sottraiamo gli eventi


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


def checkSign(auth):
    positive_sign = True
    negative_sign = True
    first_positive_sign = "+"
    first_negative_sign = "-"
    for a in auth:
        auth_ = Auth.find_one({"_id": a}, {"_id": 0, "sign": 1})
        if auth_["sign"] != first_positive_sign:
            positive_sign = False
        if auth_["sign"] != first_negative_sign:
            negative_sign = False
    return [positive_sign, negative_sign]


# Return the list of event, for the calendar CALENDAR that the user can update
# Who calls this func, must check if the user is the creator of the event, in that case, he can update everything
def eventUserCanWrite(user, calendar):
    user_group = user_to_group(user)
    events = getVisibileEventsWithHier(user, calendar, "update")
    result = []
    if len(events) != 0:
        if len(user_group) == 1:
            result = Group.find_one({"_id": user_group[0]}, {"Precondition": 1, "_id": 0})
            events = precond(result['Precondition'], events, calendar)
        else:
            for group in user_group:
                result = Group.find_one({"_id": group}, {"Precondition": 1, "_id": 0})
                events = precond(result['Precondition'], events, calendar)
        return events
    else:
        return []


@post("/list_auth")
def getAllAuth():
    query = get_query_new(request.body.read().decode('utf-8'))
    res = Auth.find({"creator": query["id"]})
    list_auth = []
    for item in res:
        list_auth.append(item)
    return json_util.dumps(list_auth)


# to update all references
@post("/delete_auth")
def deleteAuth():
    query = get_query_new(request.body.read().decode('utf-8'))
    myquery = {"_id": ObjectId(query['auth_id'])}
    ris = Auth.find_one(myquery, {"calendar_id": 1, "group_id": 1})
    res = Auth.delete_one(myquery)
    newvalues = {"$pull": {'Authorization': ris["_id"]}}
    test = Cal.find_one({"_id": ObjectId(ris["calendar_id"])})
    Cal.update_one({"_id": ObjectId(ris["calendar_id"])}, newvalues)
    if User.find_one({"_id": ObjectId(ris["group_id"])}) is None:
        Group.update_one({"_id": ObjectId(ris["group_id"])}, newvalues)
    else:
        User.update_one({"_id": ObjectId(ris["group_id"])}, newvalues)
    if res.deleted_count != 1:
        return "Errore nella cancellazione"
    return "Cancellazione completata con successo"


@post("/list_pre")
def getAllPre():
    query = get_query_new(request.body.read().decode('utf-8'))
    res = Precondition.find({"creator": query["id"]})
    list_pre = []
    for item in res:
        list_pre.append(item)
    return json_util.dumps(list_pre)


@post("/list_admin_pre")
def getAllAdminPre():
    query = get_query_new(request.body.read().decode('utf-8'))
    res = Admin_Auth.find({"creator": query["id"]})
    list_pre = []
    for item in res:
        user_name = User.find_one({"_id": ObjectId(item["user_id"])}, {"_id": 0, "username": 1})
        item.pop("user_id")
        result = {**item, **user_name}
        list_pre.append(result)
    return json_util.dumps(list_pre)


@post("/delete_admin_pre")
def deleteAdminPre():
    query = get_query_new(request.body.read().decode('utf-8'))
    myquery = {"_id": ObjectId(query['pre_id'])}
    ris = Admin_Auth.find_one(myquery, {"calendar_id": 1, "user_id": 1})
    res = Admin_Auth.delete_one(myquery)
    newvalues = {"$pull": {'Admin_auth': ris["_id"]}}
    Cal.update_one({"_id": ObjectId(ris["calendar_id"])}, newvalues)
    User.update_one({"_id": ObjectId(ris["user_id"])}, newvalues)
    if res.deleted_count != 1:
        return "Errore nella cancellazione"
    return "Cancellazione completata con successo"


# to update all references
@post("/delete_pre")
def deletePre():
    query = get_query_new(request.body.read().decode('utf-8'))
    myquery = {"_id": ObjectId(query['pre_id'])}
    ris = Precondition.find_one(myquery, {"calendar_id": 1, "group_id": 1})
    res = Precondition.delete_one(myquery)
    newvalues = {"$pull": {'Precondition': ris["_id"]}}
    Cal.update_one({"_id": ObjectId(ris["calendar_id"])}, newvalues)
    if User.find_one({"_id": ObjectId(ris["group_id"])}) is None:
        Group.update_one({"_id": ObjectId(ris["group_id"])}, newvalues)
    else:
        User.update_one({"_id": ObjectId(ris["group_id"])}, newvalues)
    if res.deleted_count != 1:
        return "Errore nella cancellazione"
    return "Cancellazione completata con successo"


def eventsADelegateCanRead(user_id, calendar_id):
    # 1. Check, is he a Delegate?
    res = Admin_Auth.find_one({"user_id": user_id, "calendar_id": calendar_id})
    if res is None:
        print("Non si tratta di un delegato")
        return []
    print("Hey, delegato, puoi vedere:")
    events = Event.find({"calendar": calendar_id})
    if events is None:
        print("Sei un delegato, ma non ci sono eventi su questo calendario")
        return []
    list_events = []
    if res["repetition"] == "true":
        timeslot = res["startDay"] + "." + res["startHour"] + ":" + res["startMin"] + "-" + res["endDay"] + "." + res[
            "endHour"] + ":" + res["endMin"]
        list_events = evaluate_rep_admin(timeslot, events)
    else:
        timeslot = res["start"] + "-" + res["end"]
        list_events = evaluate_not_rep_admin(timeslot, events)

    event_create_by_delegate = Event.find({"creator": user_id, "calendar": calendar_id})
    for event in event_create_by_delegate:
        if not isInList(list_events, event, "_id", "_id"):
            list_events.append(event)
    return list_events


# In caso di delegato, aggiungere eventi che può vedere
@post("/event_vis")
def vis():
    event_owner_cal = []
    query = get_query_new(request.body.read().decode('utf-8'))

    res = Cal.find_one({"owner": query["id"], "_id": ObjectId(query['calendar'])})
    # aggiungi tutti gli eventi contenuti nel calendario di cui è owner

    if res is not None:
        ris = Event.find({"calendar": str(res['_id'])})
        for item in ris:
            event_owner_cal.append(item)
        return json_util.dumps(event_owner_cal)

    # Se si tratta di un delegato, ritorna tutti gli eventi di quel calendario
    delegate_events = eventsADelegateCanRead(query["id"], query['calendar'])
    if len(delegate_events) != 0:
        return json_util.dumps(delegate_events)
    # Possono esserci più auth, su più gruppi
    user_group = user_to_group(query["id"])
    events = getVisibileEventsWithHier(query['id'], query['calendar'], "show")
    # print("User can write: ", eventUserCanWrite(query["id"], query["calendar"]))
    events_writable = eventUserCanWrite(query["id"], query["calendar"])

    if len(events) != 0:
        if len(user_group) == 1:
            result = Group.find_one({"_id": user_group[0]}, {"Precondition": 1, "_id": 0})
            events = precond(result['Precondition'], events, query['calendar'])
        else:
            for group in user_group:
                result = Group.find_one({"_id": group}, {"Precondition": 1, "_id": 0})
                events = precond(result['Precondition'], events, query['calendar'])
        list = [events, events_writable]
        final = create_set_union(list)
        return json_util.dumps(final)
    else:
        return []


app.install(EnableCors())
run(host='0.0.0.0', port=12345, debug=True)
