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
@post('/mod_event')
def update_events():
    query = get_query_new(request.body.read().decode('utf-8'))
    query['_id'] = ObjectId(query['_id'])
    myquery = {"_id": (query['_id'])}
    eventToUpdate = Event.find_one(myquery)
    # caso delegato e admin delegato da gestire
    if Cal.find_one({"_id": ObjectId(query['calendar']), "owner": query["username"]}):  # or \
        # search_auth_write(getAuthforUser(query['username'], query["calendar"]), eventToUpdate["_id"],
        #                 eventToUpdate["type"]):
        Event.delete_one(myquery)
        query.pop('username')
        Event.insert_one(query)
        return "Modifica completata con successo"
    return "Errore nella modifica"


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

    ##newvalues_owner_delegate = {"$set": {"title": query['title'], "allDay": query["allDay"], "calendar": query["calendar"], "color": query["color"], "type"}}
    # nel caso di Alessandro, aggiungere un controllo se l'utente è delegato admin o delegato normale, controllado nelle Admin Auth, ma questo controllo solo per modificare la data
    # if not (Cal.find_one({"_id": ObjectId(query["calendar"]), "owner": query['username']}) is None):

    # newvalues = {"$set": {"title": query['title']}}
    # Event.update_one(myquery, newvalues)
    # item = Event.find()
    # return json_util.dumps(item)


@get('/image')
def video_image():
    user_id = request.query.user
    return bottle.static_file((user_id + ".jpg"), root="", mimetype='image/jpg')


@post("/user_cal")
def user_cal():
    query = get_query_new(request.body.read().decode('utf-8'))
    list_cal = []
    list_calendar = set()
    list_group = []
    res = Cal.find({"owner": query['id']}, {"type": 1, "_id": 1})
    for item in res:
        temp = {
            "id": str(item["_id"]),
            "type": item["type"]
        }
        list_cal.append(temp)

    ris = Group.find({}, {"_id": 1, "User": 1})
    for item in ris:
        for user in item['User']:
            if user == ObjectId(query['id']):
                list_group.append(str(item['_id']))
    for item in list_group:
        result = Auth.find({"group_id": item}, {"calendar_id": 1})
        for cal in result:
            list_calendar.add(cal['calendar_id'])
    for cal in list_calendar:
        res = Cal.find({"_id": ObjectId(cal)}, {"type": 1, "_id": 1})
        temp = {
            "id": str(res[0]["_id"]),
            "type": res[0]["type"]
        }
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


def get_query(request):
    pair = []
    equal_list = []
    dollar_list = []
    for item in re.finditer('&', request):
        dollar_list.append(item.start())

    for item in re.finditer('=', request):
        equal_list.append(item.start())

    if len(dollar_list) == 0:
        pair.append(((request[0:equal_list[0]]), request[equal_list[0] + 1:len(request)]))
        return create_query(pair)
    pair.append(((request[0:equal_list[0]]), request[equal_list[0] + 1:dollar_list[0]]))
    for i in range(0, len(dollar_list) - 1):
        pair.append((request[dollar_list[i] + 1:equal_list[i + 1]], request[equal_list[i + 1] + 1:dollar_list[i + 1]]))
    pair.append((request[dollar_list[len(dollar_list) - 1] + 1:equal_list[len(dollar_list)]],
                 request[equal_list[len(dollar_list)] + 1:len(request)]))
    return create_query(pair)


# curl --data "title=Meeting(ProgettoA)&type=Meeting&start=1626858000&end=1626861600&color=#fff000&allDay=false&calendar=60f82761f748c26325297ab8" http://0.0.0.0:12345/insert_event
@post('/insert_event')
def insert_event():
    print(request.body.read().decode('utf-8'))
    query = get_query_new(request.body.read().decode('utf-8'))
    print(query)
    Event.insert_one(query)
    myquery = {'_id': ObjectId(query['calendar'])}
    res = Event.find({}, {'_id'}).sort('_id', -1).limit(1)
    newvalues = {"$addToSet": {'Events': ObjectId(res[0]['_id'])}}
    Cal.update_one(myquery, newvalues)


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
    Auth.insert_one(query)
    res = Auth.find({}, {'_id'}).sort('_id', -1).limit(1)
    newvalues = {"$addToSet": {'Authorization': ObjectId(res[0]['_id'])}}
    if User.find_one(myquery2) is None:
        Group.update_one(myquery2, newvalues)
    else:
        User.update_one(myquery2, newvalues)
    Cal.update_one(myquery, newvalues)
    return "Autorizzazione inserita con successo"


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
    query = get_query(request.body.read().decode('utf-8'))
    myquery = {'_id': ObjectId(query['calendar'])}
    myquery1 = {'_id': ObjectId(query['name'])}
    newquery = {"user_type": "delegate"}
    new_dict = {**query, **newquery}
    Admin_Auth.insert_one(new_dict)
    res = Admin_Auth.find({}, {'_id'}).sort('_id', -1).limit(1)
    newvalues = {"$addToSet": {'Admin_auth': ObjectId(res[0]['_id'])}}
    User.update_one(myquery1, newvalues)
    Cal.update_one(myquery, newvalues)


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


@post("/group_id")
def group_id():
    query = get_query(request.body.read().decode('utf-8'))
    lista = []
    res = Group.find({"name": query['name']}, {"_id": 1, "name": 1})
    for item in res:
        lista.append(str(item["_id"]) + "-" + item["name"])
    return lista


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


def evaluate_not_rep_admin(timeslot, calendar):
    [start_date, start_hour, end_date, end_hour] = string_not_repetition(timeslot)
    result = Event.find({"calendar": calendar})
    good_event = []
    for item in result:
        start = datetime.fromtimestamp(int(item["start"]))
        end = datetime.fromtimestamp(int(item["end"]))
        if not (datetime.date(start) > end_date or datetime.date(end) < start_date):
            if not (datetime.time(start) > end_hour or datetime.time(end) < start_hour):
                good_event.append(item)
    return good_event


def evaluate_rep_admin(timeslot, calendar):
    [start_day, start_hour, end_day, end_hour] = string_repetition(timeslot)
    result = Event.find({"calendar": calendar})
    good_event = []
    for item in result:
        start = datetime.fromtimestamp(int(item["start"]))
        end = datetime.fromtimestamp(int(item["end"]))
        start_hour_adm = datetime.strptime(start_hour, "%H:%M").time()
        end_hour_adm = datetime.strptime(end_hour, "%H:%M").time()
        if not (int(datetime.weekday(start)) > int(end_day) or int(datetime.weekday(end)) < int(start_day)):
            if not (datetime.time(start) > end_hour_adm or datetime.time(end) < start_hour_adm):
                good_event.append(item)
    return good_event


# -------------------------------------------------------------------------------------------------------
def evaluate_not_rep(timeslot, eventi):
    [start_date, start_hour, end_date, end_hour] = string_not_repetition(timeslot)
    good_event = []
    print(eventi)
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


def manage_conflict_auth(autorizzazioni):
    auth = []
    print(autorizzazioni)
    for i in autorizzazioni:
        auth.append((i['_id'], i['segno']))
    print(auth)


# TODO conflitto
def authorization_filter(id_auth, calendario):
    eventi_good = []
    flag = False
    auth = Auth.find_one({"_id": ObjectId(id_auth)},
                         {'calendar_id': 1, 'condition': 1, 'sign': 1, "auth": 1, "type_auth": 1})

    if auth["type_auth"] == "freeBusy":
        eventi = Event.find({'calendar': calendario}, {"title": 1, "start": 1, "end": 1, "allDay": 1, "color": 1})
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
                    eventi_good.append(item)

        elif auth["auth"] == "evento":
            if item['_id'] == ObjectId(auth['condition']):
                if auth['sign'] == '+':
                    eventi_good.append(item)
            else:
                if auth['sign'] == '-':
                    eventi_good.append(item)
    return eventi_good


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


def solve_conflict(group_auth, calendar):
    # Se esiste solo una auth, restituisci quella, altrimenti, risolvi conflitto
    if group_auth is None:
        return []
    elif len(group_auth["Authorization"]) == 1:
        return group_auth
    else:
        return group_auth


def getVisibileEventsWithHier(user, calendar):
    # otteniamo proprietario del calendario e la sua relativa gerarchia
    owner_Cal = Cal.find_one({"_id": ObjectId(calendar)}, {"_id": 0, "owner": 1})
    G = getG(owner_Cal["owner"])
    # otteniamo la lista dei gruppi a cui l'utente appartiene
    g_id = (user_to_group(user))
    for group in g_id:
        group_name = Group.find_one({"_id": group}, {"_id": 0, "name": 1})
    n = group_name["name"]
    # ciclichiamo sul grafo alla ricerca di altre autorizzazioni, che verranno ereditate, partendo dal gruppo più
    # vicino all'utente
    groups_auth = []
    # salviamo le autorizzazioni del gruppo più vicino all'utente e risolviamo conflitti, se ne esistono
    auth_for_group = Group.find_one({"name": n, "creator": owner_Cal["owner"]},
                                    {"_id": 0, "Authorization": 1})
    groups_auth.append((solve_conflict(auth_for_group, calendar)))
    while n != "ANY":
        for node in G.successors(n):
            n = node
            # salviamo le autorizzazioni dei gruppi più alti in gerarchia e risolviamo conflitti, se ne esistono
            auth_for_group = Group.find_one({"name": node, "creator": owner_Cal["owner"]},
                                            {"_id": 0, "Authorization": 1})
            groups_auth.append((solve_conflict(auth_for_group, calendar)))
    no_event = True
    for item in groups_auth:
        if len(item) != 0:
            no_event = False
    # Se non esistono eventi visualizzabili, ritorna lista vuota
    if no_event:
        return []

    events = []
    events_evaluated = []
    events_group = []
    # analizza tutti i segni delle autorizzazioni, per capire se sono concordi o discordi
    for auth in groups_auth:
        if len(auth) != 0:
            events_group = []
            [positive_sign, negative_sign] = checkSign(auth["Authorization"])
            for a in (auth["Authorization"]):
                events_group.append(authorization_filter(a, calendar))

            # if same sign = union; else, intersection
            if positive_sign:
                events_evaluated.append((create_set_union(events_group), "+"))
            else:
                events_evaluated.append((create_set_intersect(events_group), "-"))

    result = []
    for i in range(0, len(events_evaluated)-1, 1):
        list_temp = [events_evaluated[i][0], events_evaluated[i + 1][0]]
        if events_evaluated[i][1] == "+":
            result = create_set_union(list_temp)
        else:
            result = create_set_intersect(list_temp)
    return result

    # Recuperiamo tutti i gruppi fino ad ANY, da G
    # Ottenuti tutti i gruppi, è necessario recuperare tutte le autorizzazioni associate a ogni gruppo
    # Salviamo, quindi, tutti gli eventi visibili, autorizzazioni per autorizzazione e, volta per volta, a seconda del tipo/segno uniamo o sottraiamo gli eventi


def isInList(list, element):
    for el in list:
        if el["_id"] == element["_id"]:
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
                if not isInList(list_events, temp_item):
                    list_events.append(temp_item)
    return list_events


def create_set_union(events):
    list_events = []
    for item in events:
        for temp_item in item:
            if not isInList(list_events, temp_item):
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

    # Possono esserci più auth, su più gruppi
    user_group = user_to_group(query["id"])
    events = getVisibileEventsWithHier(query['id'], query['calendar'])
    result = []
    if len(events) != 0:
        if len(user_group) == 1:
            result = Group.find_one({"_id": user_group[0]}, {"Precondition": 1, "_id": 0})
            events = precond(result['Precondition'], events, query['calendar'])
        else:
            for group in user_group:
                result = Group.find_one({"_id": group}, {"Precondition": 1, "_id": 0})
                events = precond(result['Precondition'], events, query['calendar'])
        return json_util.dumps(events)
    else:
        return []


app.install(EnableCors())
run(host='0.0.0.0', port=12345, debug=True)
