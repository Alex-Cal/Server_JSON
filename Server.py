import time
import json
import re
from datetime import datetime

from bottle import run, request, post, get, app, response, route
from bottle_cors_plugin import cors_plugin
import pymongo
import bottle
from bson import json_util, ObjectId

# Connection to MongoDB
myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["CalendarDB"]
Cal = mydb["Calendar"]
Event = mydb["Events"]
Precondition = mydb["Temporal Pre-Condition"]
Admin_Auth = mydb["Admin_Auth"]
Auth = mydb["Authorization"]
User = mydb["User"]
Group = mydb["Group"]


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


# shows all events
@post('/')
def index():
    return json_util.dumps(Event.find())


# shows all calendar
@post('/cal')
def calendar():
    return json_util.dumps(Cal.find())


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


# shows all events given calendar
@post('/list_cal_event_multiple')
def list_event():
    items_ev = []
    res = []
    s = []
    a = []
    temp_type = request.params.get('type')

    type = get_all_types(temp_type)
    # Now, type is a list of this form: ['Scuola', 'Work'], so you must make multiple queries (or a single query with an OR operator)
    for i in type:
        items = Cal.find({'type': i}, {'Events': 1})
        res.append(items[0]['Events'])
    for x in res:
        for y in x:
            items_ev.append(Event.find({'_id': y}))
    for i in items_ev:
        s.append(str(json_util.dumps(i)))
    return (str(s).replace("'[", '')).replace("]'", '')


# list one type event
@post('/list_cal_event')
def list_one_type_event():
    items_ev = []
    type = request.params.get('type')
    items = Cal.find({'type': type}, {'Events': 1})
    res = items[0]['Events']
    for x in res:
        items_ev.append(Event.find({'_id': x}))
    s = str(json_util.dumps(items_ev))
    a = ((s.replace('[', '')).replace(']', ''))
    return "[" + a + "]"


# modify a given event title
@post('/mod_event')
def update_events():
    query = get_query_new(request.body.read().decode('utf-8'))
    print(query)
    lista = []


    query['_id'] = ObjectId(query['_id'])
    Event.find_one({"_id": query["_id"]}, {"start": 1, "end": 1})
    print("Posso modificare?")
    myquery = {"_id": (query['_id'])}
    #caso delegato e admin delegato da gestire
    if Cal.find_one({"_id": ObjectId(query['calendar']), "owner": query["username"]}):
        Event.delete_one(myquery)
        query.pop('username')
        Event.insert_one(query)


    else:
        search_auth_write(user_to_group_cal(query['username'], query["calendar"]))



def search_auth_write(auth):
    print(auth)
    for autorization in auth:
        #conflitti
        print(json_util.dumps(Auth.find({"subject": autorization[0], "type_auth": "write", "sign": "+"})) is None)
        if not(Auth.find({"_id": ObjectId(autorization[1]), "type_auth": "write", "sign": "+"})) is None:
            return True
    return False


    ##newvalues_owner_delegate = {"$set": {"title": query['title'], "allDay": query["allDay"], "calendar": query["calendar"], "color": query["color"], "type"}}
    #nel caso di Alessandro, aggiungere un controllo se l'utente è delegato admin o delegato normale, controllado nelle Admin Auth, ma questo controllo solo per modificare la data
    #if not (Cal.find_one({"_id": ObjectId(query["calendar"]), "owner": query['username']}) is None):


    #newvalues = {"$set": {"title": query['title']}}
    #Event.update_one(myquery, newvalues)
    #item = Event.find()
    #return json_util.dumps(item)


@post("/user_cal")
def user_cal():
    query = get_query_new(request.body.read().decode('utf-8'))
    list_cal = []
    list_calendar = []
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
        result = Auth.find({"subject": item}, {"calendar": 1})
        for cal in result:
            list_calendar.append(cal['calendar'])
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
    if(ris.deleted_count != 1):
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
    query = get_query(request.body.read().decode('utf-8'))
    query2 = {"Events": [], "Precondition": [], "Admin_auth": [], "Authorization": []}
    new_dict = {**query, **query2}
    Cal.insert_one(new_dict)


# curl --data "name=Bob&Surname=Red" http://0.0.0.0:12345/insert_user
@post('/insert_user')
def insert_user():
    query = get_query(request.body.read().decode('utf-8'))
    query2 = {"Group": [], "Precondition": [], "Admin_auth": [], "Authorization": []}
    new_dict = {**query, **query2}
    User.insert_one(new_dict)


@post('/insert_group')
def insert_group():
    query = get_query(request.body.read().decode('utf-8'))
    query2 = {"User": [], "Precondition": [], "Authorization": []}
    new_dict = {**query, **query2}
    Group.insert_one(new_dict)


@post("/list_us")
def list_us():
    res = User.find({}, {"name": 1, "_id": 0})
    return json_util.dumps(res)


# curl --data "id=1&subject=Carol&calendar=School&type_event=Lezione&prop=null&type_auth=read&sign=+" http://0.0.0.0:12345/ins_auth
@post("/ins_auth")
def insert_auth():
    query = get_query(request.body.read().decode('utf-8'))
    myquery = {'_id': ObjectId(query['calendar'])}
    myquery2 = {'_id': ObjectId(query['subject'])}
    Auth.insert_one(query)
    res = Auth.find({}, {'_id'}).sort('_id', -1).limit(1)
    newvalues = {"$addToSet": {'Authorization': ObjectId(res[0]['_id'])}}
    if User.find_one(myquery2) is None:
        Group.update_one(myquery2, newvalues)
    else:
        User.update_one(myquery2, newvalues)
    Cal.update_one(myquery, newvalues)


@post('/precondition')
def insert_precondition():
    query = get_query(request.body.read().decode('utf-8'))
    myquery = {'_id': ObjectId(query['calendar'])}
    myquery1 = {'_id': ObjectId(query['name'])}
    newquery = {"user_type": "collaborator"}
    new_dict = {**query, **newquery}
    Precondition.insert_one(new_dict)
    res = Precondition.find({}, {'_id'}).sort('_id', -1).limit(1)
    newvalues = {"$addToSet": {'Precondition': ObjectId(res[0]['_id'])}}

    if (User.find_one(myquery1)) is None:
        Group.update_one(myquery1, newvalues)
    else:
        User.update_one(myquery1, newvalues)
    Cal.update_one(myquery, newvalues)


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


@post("/insert_user_group")
def insert_user_group():
    query = get_query(request.body.read().decode('utf-8'))
    if User.find_one({"_id": ObjectId(query["user"])}) is None:
        return "Utente inesistente"
    else:
        if not (Group.find_one({'_id': ObjectId(query['group'])})) is None:
            newvalues = {"$addToSet": {'User': ObjectId(query['user'])}}
            Group.update_one({'_id': ObjectId(query['group'])}, newvalues)
        else:
            return "Gruppo inesistente"


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


def authorization_filter(id_auth, calendario):
    eventi_good = []
    auth = Auth.find_one({"_id": ObjectId(id_auth)},
                         {'calendar': 1, 'type_event': 1, 'sign': 1})
    eventi = Event.find({'calendar': calendario})
    for item in eventi:
        if auth['sign'] == '+':
            if item['type'] == auth['type_event']:
                eventi_good.append(item)
        elif auth['sign'] == '-':
            if item['type'] != auth['type_event']:
                eventi_good.append(item)
    return eventi_good


def precond(pre, eventi, calendar):
    for i in pre:
        timeslot = Precondition.find_one({"_id": i, "calendar": calendar},
                                         {"timeslot": 1, "_id": 0, "type_time": 1})
        if timeslot is None:
            return eventi
        if timeslot["type_time"] == "repetition":
            return evaluate_rep(timeslot['timeslot'], eventi)
        else:
            return evaluate_not_rep(timeslot['timeslot'], eventi)


def auth_adm(auth, query):
    for i in auth:
        timeslot = Admin_Auth.find_one({"_id": i},
                                       {"timeslot": 1, "_id": 0, "type_time": 1})
        if timeslot["type_time"] == "repetition":
            return evaluate_rep_admin(timeslot['timeslot'], query['calendar'])

        else:
            return evaluate_not_rep_admin(timeslot['timeslot'], query['calendar'])

#in caso di utente appartente a più gruppi che agiscono sullo stesso calendario, restutisco l'ID del gruppo più vicino in gerarchia
def user_to_group_cal(user, calendar):
    res = Group.find({}, {"_id": 1, "User": 1})
    g = []
    good_group = []
    for group in res:
        for user_id in group['User']:
            if user == str(user_id):
                g.append(group['_id'])
    for group in g:
        res = Auth.find({"subject": str(group), "calendar": calendar}, {"_id": 1})
        for auth in res:
            good_group.append((group, auth["_id"]))
    return good_group


def evaluate_auth(auth):
    #N.B: se len == 1 e segno = +
    if len(auth) == 1:
        return auth
    return auth

@post("/event_vis")
def vis():
    query = get_query_new(request.body.read().decode('utf-8'))
    res = []
    cond = False
    #controlla che sia delegato
    group_auth = user_to_group_cal(query['id'], query['calendar'])
    if group_auth is None:
        return []

    winning_auth = evaluate_auth(group_auth)
    if len(winning_auth) ==0:
        return []
    print(winning_auth)
    events = authorization_filter(winning_auth[0][1], query['calendar'])
    print(events)
    result = Group.find_one({"_id": ObjectId(winning_auth[0][0])}, {"Precondition": 1, "_id": 0})
    eventi = precond(result['Precondition'], events, query['calendar'])

    return json_util.dumps(eventi)


    # if (User.find_one({"_id": ObjectId(query['name'])})) is None:
    #     result = Group.find_one({"_id": ObjectId(query['name'])}, {"Precondition": 1, "Authorization": 1, "_id": 0})
    #     for j in result['Authorization']:
    #         if not (Auth.find_one({"_id": j}, {"_id": 1}) is None):
    #             cond = True
    #
    #     # manage_conflict_auth(result['Authorization'])
    #     # dopo aver gestito l'eventuale conflitto, avrò l'id dell'autorizzazione da applicare e passare alla funzione successiva
    #     events = authorization_filter(query['name'], query['calendar'])
    #     if cond:
    #         res = precond(result['Precondition'], events)
    #     else:
    #         return None
    #
    # else:
    #     if not (Admin_Auth.find_one({"name": query['name'], "calendar": query['calendar']}, {}) is None):
    #         result = User.find_one({"_id": ObjectId(query['name'])}, {"Admin_auth": 1, "_id": 0})
    #         res = auth_adm(result['Admin_auth'], query)
    #     else:
    #         result = User.find_one({"_id": ObjectId(query['name'])}, {"Precondition": 1, "Authorization": 1, "_id": 0})
    #         for j in result['Authorization']:
    #             if not (Auth.find_one({"_id": j}, {"_id": 1}) is None):
    #                 cond = True
    #
    #         events = authorization_filter(query['name'], query['calendar'])
    #         if cond:
    #             res = precond(result['Precondition'], events)
    #         else:
    #             return None


app.install(EnableCors())
run(host='0.0.0.0', port=12345, debug=True)
