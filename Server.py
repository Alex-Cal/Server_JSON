from Utility import Utils, PreCondUtils, EventViewerUtils, ClashUtils, StringUtils, HierarchyUtils, Connections

import networkx as nx
from bottle import run, request, post, get, response
import bottle
from bottle_cors_plugin import cors_plugin
from bson import json_util, ObjectId


# Abilita, per ogni richiesta, header di risposta con CORS
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

# Servizio che restituisce tutti i tipi degli eventi creati (utile nella definizione di auth basate sul tipo)
@post('/all_type_event')
def all_type():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    res = Connections.getEvent().find({"creator": query["id"]}, {"type": 1})
    lista_event = set()
    for item in res:
        lista_event.add(item["type"])
    return json_util.dumps(lista_event)


# Servizio che restituisce titolo ed id di tutti gli eventi di un determinato calendario (utile nella definizione di auth basate sul singolo evento)
@post("/calendar_event")
def cal_event():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    res = Connections.getEvent().find({"calendar": query['calendar']}, {"_id": 1, "title": 1})
    lista_event = []
    for item in res:
        lista_event.append(item)
    return json_util.dumps(lista_event)

# Servizio che permette la modifica di un evento precedentemente creato, tenendo conto del ruolo dell'utente rispetto all'evento creato
@post('/mod_event')
def update_events():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    query['_id'] = ObjectId(query['_id'])
    myquery = {"_id": (query['_id'])}
    eventToUpdate = Connections.getEvent().find_one(myquery)

    present_delegate = False
    present_user = False

    existAuth = Connections.getAdmin_Auth().find_one({"user_id": query["username"], "calendar_id": query["calendar"]})
    isOwner = Connections.getCal().find_one({"_id": ObjectId(query['calendar']), "owner": query["username"]})

    # L'owner del calendario può sempre modificare tutti gli eventi sul suo calendario
    if isOwner is not None:
        #quello che modifica diventa il creator dell'evento
        query["creator"] = query["username"]
        query.pop('username')
        Connections.getEvent().delete_one(myquery)
        Connections.getEvent().insert_one(query)
        return "Modifica completata con successo"

    # Se sei un delegato del calendario X, bisogna controllare l'evento che vuoi modificare
    # Se l'evento ha come creator un delegato ADMIN e tu sei un delegato ROOT,  lo modifichi
    # Se sei un delegato ADMIN e l'evento è stato creato da te, allora puoi modificarlo
    # Se sei delegato ROOT e l'evento è creato da qualsiasi persona, all'infuori dell'owner, puoi modificarlo

    # Se esiste una auth da delegato (aka, se sei un delegato)
    elif existAuth is not None:
        checkAminDel = Connections.getAdmin_Auth().find_one({"user_id": eventToUpdate["creator"], "calendar_id": query["calendar"]})
        if checkAminDel is not None:
            if (checkAminDel["level"] == "DELEGATO_ADMIN" and existAuth["level"] == "DELEGATO_ROOT") or \
                    (eventToUpdate["creator"] == query["username"]) or \
                    (existAuth["level"] == "DELEGATO_ADMIN" and eventToUpdate["creator"] == existAuth["user_id"]):
                present_delegate = True
    else:
        # Controlla, se non sei un delegato, se hai una auth di scrittura per quell'evento
        event_user_can_update = EventViewerUtils.eventUserCanWrite(query["username"], query["calendar"])
        for item in event_user_can_update:
            if item["_id"] == query["_id"]:
                present_user = True

    # Se sei un delegato, puoi modificare, ma è necessario controllare che il nuovo timeslot (se sei un delegato), sia compatibile con l'auth da delegato
    if present_delegate:
        #quello che modifica diventa il creator dell'evento
        query["creator"] = query["username"]
        query.pop('username')
        Connections.getEvent().delete_one(myquery)
        canUpdDateTime = PreCondUtils.canADelegateAccessTimeslot(query["creator"], query["calendar"], query["start"], query["end"])
        # Se il timeslot non viene modificato, l'evento modificato può essere inserito senza problemi
        if (query["start"] == eventToUpdate["start"] and query["end"] == eventToUpdate["end"]) or canUpdDateTime:
            if canUpdDateTime:
                # Se la modifica del timeslot genera un clash, questo viene gestito e, di conseguenza, l'inserimento è funzionale all'esito del clash
                if ClashUtils.isThereAConflict(query["calendar"], query["start"], query["end"], query["creator"]) == "T":
                    Connections.getEvent().insert_one(query)
                    return "Evento modificato"
            # Se il timeslot non viene modificato, si inserisce il vecchio timeslot
            query["start"] = eventToUpdate["start"]
            query["end"] = eventToUpdate["end"]
            Connections.getEvent().insert_one(query)
            return "Timeslot dell'evento non modificato a causa di clash, ripristinato il timeslot originale"
        elif not canUpdDateTime:
            # Se l'utente non può modificare il timeslot, viene settato quello originale
            query["start"] = eventToUpdate["start"]
            query["end"] = eventToUpdate["end"]
            Connections.getEvent().insert_one(query)
            return "Errore nella modifica, timeslot invariato"
    # Se non si è delegato, ma utente con auth di scrittura, modifica l'evento, senza modificare il timeslot
    elif present_user:
        Connections.getEvent().delete_one(myquery)
        query.pop('username')
        query["start"] = eventToUpdate["start"]
        query["end"] = eventToUpdate["end"]
        Connections.getEvent().insert_one(query)
        return "Modifica completata con successo (timeslot invariato)"
    return "Errore nella modifica"

# Servizio che restituisce, per ogni utente, l'immagine associata alla gerarchia da lui creata
@get('/image')
def video_image():
    user_id = request.query.user
    G = HierarchyUtils.getG(user_id)
    HierarchyUtils.save_image(G, user_id)
    return bottle.static_file((user_id + ".jpg"), root="", mimetype='image/jpg')

# Servizio che restituisce, per ogni utente, la lista dei calendari a lui accessibile
@post("/user_cal")
def user_cal():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    list_cal = []
    list_calendar = set()
    list_group = []
    groups_hier = []
    # Si recuperano prima tutti i calendari di cui l'utente è owner


    res = Connections.getCal().find({"owner": query['id']}, {"type": 1, "xor": 1, "_id": 1})
    for item in res:
        temp = {
            "id": str(item["_id"]),
            "type": item["type"],
            "xor": item["xor"]
        }
        list_cal.append(temp)

    # calendari per cui l'utente è delegato
    res = Connections.getCal().find({}, {"Admin_auth": 1, "_id": 1, "type": 1, "xor": 1})
    for item in res:
        for auth in item["Admin_auth"]:
            admin_auth = Connections.getAdmin_Auth().find_one({"_id": ObjectId(auth)})
            if query["id"] == admin_auth["user_id"]:
                temp = {
                    "id": str(item["_id"]),
                    "type": item["type"],
                    "xor": item["xor"]
                }
                list_cal.append(temp)

    # Si recuperano i gruppi a cui l'utente appartiene e su cui esistono delle autorizzazioni di visibilità
    ris = Connections.getGroup().find({}, {"_id": 1, "User": 1})
    for item in ris:
        for user in item['User']:
            if user == ObjectId(query['id']):
                list_group.append(str(item['_id']))

    # calendari a cui l'utente non ha accesso diretto, ma eredita l'accesso dalla gerarchia
    # In questo caso, si accede alla gerarchia associata, per recuperare i gruppi a cui appartiene in gerarchia
    for group in list_group:
        res = Connections.getGroup().find({"_id": ObjectId(group)}, {"creator": 1, "name": 1})
        for g in res:
            G = HierarchyUtils.getG(g["creator"])
            n = Utils.getGroupName(group)["name"]
            while n != "ANY":
                for node in G.successors(n):
                    n = node
                    group_find = Connections.getGroup().find_one({"name": node, "creator": g["creator"]}, {"_id": 1})
                    if group_find is not None:
                        groups_hier.append(str(group_find["_id"]))

    # Si uniscono i gruppi derivati dalla gerarchia e quelli derivati dalle autorizzazioni
    complete_groups = groups_hier + list_group

    # Si recuperano i calendari associati a questi gruppi e sono in un set
    for item in complete_groups:
        result = Connections.getAuth().find({"group_id": item}, {"calendar_id": 1})
        for cal in result:
            list_calendar.add(cal['calendar_id'])

    # Si trasforma il set in una lista json senza duplicati e la si restistuisce
    for cal in list_calendar:
        res = Connections.getCal().find_one({"_id": ObjectId(cal)}, {"type": 1, "_id": 1, "xor": 1})
        temp = {
            "id": str(res["_id"]),
            "type": res["type"],
            "xor": res["xor"]
        }
        if not Utils.isInList(list_cal, temp, "id", "id"):
            list_cal.append(temp)

    return json_util.dumps(list_cal)


# Servizio che offre la cancellazione di un evento
@post('/delete_event')
def delete_event():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    myquery = {"_id": ObjectId(query['_id'])}
    res = Connections.getEvent().find_one(myquery)
    canDelete = False
    # Se l'utente è il creatore dell'evento e l'evento non ha generato clash, può rimuoverlo; se non è il creatore, ma è l'owner del calendario, può rimuoverlo sempre
    if res is not None:
        if res["creator"] != query["user"]:
            cal = Connections.getCal().find_one({"_id": ObjectId(res["calendar"])})
            if cal is not None:
                if cal["owner"] == query["user"]:
                    canDelete = True
        else:
            # Se il colore = #ff2400, indica che c'è stato un clash
            if res["color"] != "#ff2400":
                canDelete = True

    if canDelete:
        ris = Connections.getEvent().delete_one(myquery)
        new_query = {"_id": ObjectId(res['calendar'])}
        Connections.getCal().update_one(new_query, {"$pull": {'Events': ObjectId(query['_id'])}})
        if ris.deleted_count != 1:
            return "Errore nella cancellazione"
        return "Cancellazione completata con successo"
    return "Errore nella cancellazione"


# Servizio che permette l'inserimento di un evento, controllando sia clash, sia autorizzazioni
@post('/insert_event')
def insert_event():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    isOwner = Connections.getCal().find_one({"_id": ObjectId(query['calendar']), "owner": query["creator"]})
    # L'owner del calendario può sempre inserire eventi sul suo calendario, senza limiti
    if isOwner is not None:
        Connections.getEvent().insert_one(query)
        myquery = {'_id': ObjectId(query['calendar'])}
        res = Connections.getEvent().find({}, {'_id'}).sort('_id', -1).limit(1)
        newvalues = {"$addToSet": {'Events': ObjectId(res[0]['_id'])}}
        Connections.getCal().update_one(myquery, newvalues)
        return "Inserimento completato con successo (owner del calendario)"

    # Se non si tratta di owner, controlla che si tratti di un delegato
    existAuth = Connections.getAdmin_Auth().find_one({"user_id": query["creator"], "calendar_id": query["calendar"]})
    if existAuth is not None:
        isAble = PreCondUtils.canADelegateAccessTimeslot(query["creator"], query["calendar"], query["start"], query["end"])
        if isAble:
            # canSet indica l'esito della valutazione del clash, dove T= no clash (o clash con inserimento concesso), EX indica clash su due calendari esclusivi e uso del colore per indicare il calsh
            canSet = ClashUtils.isThereAConflict(query["calendar"], query["start"], query["end"], query["creator"])
            if canSet == "T":
                Connections.getEvent().insert_one(query)
                myquery = {'_id': ObjectId(query['calendar'])}
                res = Connections.getEvent().find({}, {'_id'}).sort('_id', -1).limit(1)
                newvalues = {"$addToSet": {'Events': ObjectId(res[0]['_id'])}}
                Connections.getCal().update_one(myquery, newvalues)
                return "Inserimento completato con successo (delegato e giusto intervallo)"
            elif canSet == "EX":
                #setta il colore per indicare il clash
                query["color"] ="#ff2400"
                Connections.getEvent().insert_one(query)
                myquery = {'_id': ObjectId(query['calendar'])}
                res = Connections.getEvent().find({}, {'_id'}).sort('_id', -1).limit(1)
                newvalues = {"$addToSet": {'Events': ObjectId(res[0]['_id'])}}
                Connections.getCal().update_one(myquery, newvalues)
                return "Inserimento in due calendari esclusivi; inserimento permesso, con riserva di decisione per l'owner"
            else:
                return "Presente un clash, errore nell'inserimento"
        else:
            return "Errore nell'inserimento, timeslot a te non disponibile"
    return "Errore nell'inserimento"


# Servizio che permette l'inserimento di un nuovo calendario
@post('/insert_cal')
def insert_cal():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    query2 = {"Events": [], "Precondition": [], "Admin_auth": [], "Authorization": []}
    new_dict = {**query, **query2}
    Connections.getCal().insert_one(new_dict)
    return "Inserimento del calendario avvenuto con successo"

# Servizio che restituisce la lista di calendari di cui l'utente è owner
@post('/list_cal_owner')
def cal_owner():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    list_cal = []
    res = Connections.getCal().find({"owner": query['id']}, {"type": 1, "_id": 1})
    for item in res:
        list_cal.append(item)
    return json_util.dumps(list_cal)


# Servizio che permette l'inserimento di un nuovo utente e generazione della gerarchia ad esso associato
# Server di login/register è diverso da questo, per cui, quando si logga con un nuovo utente per la prima volta, viene aggiunto il record del nuovo utente
@post('/insert_user')
def insert_user():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    node = [
        {"node_value": "ANY"},
    ]
    query["_id"] = ObjectId(query["_id"])
    query2 = {"Group": [], "Precondition": [], "Admin_auth": [], "Authorization": []}
    new_dict = {**query, **query2}
    if Connections.getUser().find_one({"_id": query['_id']}) is None:
        Connections.getUser().insert_one(new_dict)
        query_id = {"owner": str(query["_id"]), "Hier": []}
        G = nx.DiGraph()
        G.add_node("ANY")
        HierarchyUtils.save_image(G, str(query["_id"]))
        Connections.getHier().insert_one(query_id)
        update = {"$addToSet": {'Hier': {"node": "ANY", "belongsto": ""}}}
        query = {'owner': str(query["_id"])}
        Connections.getHier().update_one(query, update)


# Servizio che permette di aggiungere un gruppo (precedentemente creato) alla gerarchia
@post("/add_group_hier")
def group_hier():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    id = query["id"]
    update = {"$addToSet": {'Hier': {"node": query["son"], "belongsto": query["dad"]}}}
    query = {'owner': query["id"]}
    Connections.getHier().update_one(query, update)
    G = HierarchyUtils.getG(id)
    HierarchyUtils.save_image(G, id)


# Servizio che permette l'inserimento di un nuovo gruppo
@post('/insert_group')
def insert_group():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    query2 = {"User": [], "Precondition": [], "Authorization": []}
    new_dict = {**query, **query2}
    if Connections.getGroup().find_one({"name": query["name"], "creator": query["creator"]}) is None:
        Connections.getGroup().insert_one(new_dict)
        return "Gruppo inserito con successo"
    return "Impossibile inserire il gruppo"


#Servizio che permette l'inserimento di una autorizzazione di visibilità
@post("/ins_auth")
def insert_auth():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    myquery = {'_id': ObjectId(query['calendar_id'])}
    myquery2 = {'_id': ObjectId(query['group_id'])}
    # Possibilità di inserire una auth anche per un delegato (si noti che un Delegato_ADMIN può inserire solo auth di tipo read)
    isDelegate = Connections.getAdmin_Auth().find_one({"user_id": query["creator"], "calendar_id": query["calendar_id"]})
    if isDelegate is not None:
        if isDelegate["level"] == "DELEGATO_ADMIN" and query["type_auth"] == "write":
            return "Impossibile inserire l'autorizzazione"

    Connections.getAuth().insert_one(query)
    res = Connections.getAuth().find({}, {'_id'}).sort('_id', -1).limit(1)
    newvalues = {"$addToSet": {'Authorization': ObjectId(res[0]['_id'])}}
    if Connections.getUser().find_one(myquery2) is None:
        Connections.getGroup().update_one(myquery2, newvalues)
    else:
        Connections.getUser().update_one(myquery2, newvalues)
    Connections.getCal().update_one(myquery, newvalues)
    return "Autorizzazione inserita con successo"

# Servizio che restituisce tutti i calendari per cui un utente è delegato
@post('/calendar_delegate')
def calendar_delegate():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    res = Connections.getAdmin_Auth().find({"user_id": query["id"]}, {"calendar_id": 1})
    calend = []
    for calendar in res:
        cal = Connections.getCal().find_one({"_id": ObjectId(calendar["calendar_id"])}, {"_id": 1, "type": 1})
        calend.append(cal)
    return json_util.dumps(calend)

# Servizio che permette l'inserimento di una precondizione
@post('/precondition')
def insert_precondition():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    myquery = {'_id': ObjectId(query['calendar_id'])}
    myquery1 = {'_id': ObjectId(query['group_id'])}
    # Adattamento della query, alla precondizione, in modo da avere solo il campo timeslot
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
    Connections.getPrecondition().insert_one(new_dict)
    res = Connections.getPrecondition().find({}, {'_id'}).sort('_id', -1).limit(1)
    newvalues = {"$addToSet": {'Precondition': ObjectId(res[0]['_id'])}}

    if (Connections.getUser().find_one(myquery1)) is None:
        Connections.getGroup().update_one(myquery1, newvalues)
    else:
        Connections.getUser().update_one(myquery1, newvalues)
    Connections.getCal().update_one(myquery, newvalues)
    return "Precondizione inserita"

# Servizio che permette l'inserimento di una auth amministrativa (concessione della delega)
@post('/auth_admin')
def insert_admin_auth():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    existUser = Connections.getUser().find_one({"username": query["username"]})
    if existUser is None:
        return "Utente inesistente"
    if existUser["_id"] == ObjectId(query["creator"]):
        return "Impossibile delegare l'owner"
    print(query)

    existAuth = Connections.getAdmin_Auth().find_one({"user_id": str(existUser["_id"]), "calendar_id": query["calendar_id"]})
    if existAuth is not None:
        return "È già presente una autorizzazione per questo utente, su questo calendario"

    query.pop('username')
    user_id = {"user_id": str(existUser["_id"])}
    to_insert = {**query, **user_id}
    Connections.getAdmin_Auth().insert_one(to_insert)

    res = Connections.getAdmin_Auth().find({}, {'_id'}).sort('_id', -1).limit(1)
    newvalues = {"$addToSet": {'Admin_auth': ObjectId(res[0]['_id'])}}
    myquery = {'_id': ObjectId(query['calendar_id'])}
    myquery1 = {'_id': existUser["_id"]}
    Connections.getUser().update_one(myquery1, newvalues)
    Connections.getCal().update_one(myquery, newvalues)
    return "Autorizzazione inserita con successo"

# Servizio che restituisce tutti i gruppi creati da un determinato utente
@post('/list_created_group')
def list_group():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    lista_group_id = []
    res = Connections.getGroup().find({"creator": query["id"]}, {"name": 1, "_id": 1})
    if res is None:
        return []
    for item in res:
        lista_group_id.append(item)
    return json_util.dumps(lista_group_id)

# Servizio che permette di inserire un utente (se esiste) in un gruppo
@post("/insert_user_group")
def insert_user_group():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    res = Connections.getCal().find_one({"owner": query["id"]})
    if res is None:
        return "Operazione non autorizzata"
    else:
        res = Connections.getUser().find_one({"username": query["user"]}, {"_id": 1})
        if res is None:
            return "Utente inesistente"
        else:
            if (Connections.getGroup().find_one({'_id': ObjectId(query['group'])})) is not None:
                newvalues = {"$addToSet": {'User': res['_id']}}
                Connections.getGroup().update_one({'_id': ObjectId(query['group'])}, newvalues)
            else:
                return "Gruppo inesistente"
    return "Utente inserito correttamente nel gruppo"


# Servizio che restituisce tutti gli eventi che un delegato può visualizzare (utilizzato nella creazione di auth da parte del delegato)
@post("/events_delegate")
def eventsCanView():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    delegate_events = EventViewerUtils.eventsADelegateCanRead(query["id"], query["calendar_id"])
    if len(delegate_events) != 0:
        return json_util.dumps(delegate_events)

# Servizio che restituisce tutti i tipi degli eventi che un delegato può visualizzare (utilizzato nella creazione di auth da parte del delegato)
@post("/types_delegate")
def eventsCanView():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    delegate_events = EventViewerUtils.eventsADelegateCanRead(query["id"], query["calendar_id"])
    types = set()
    if len(delegate_events) != 0:
        for item in delegate_events:
            types.add(item["type"])
        return json_util.dumps(types)

# Servizio che restituisce tutti i gruppi associati ad un calendario (utile per la creazione di auth)
@post("/groups_delegate")
def groups_delegate():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    res = Connections.getAuth().find({"calendar_id": query["calendar_id"]}, {"group_id": 1, "_id": 0})
    g = []
    for groups in res:
        group = Connections.getGroup().find_one({"_id": ObjectId(groups["group_id"])}, {"_id": 1, "name": 1})
        if not Utils.isInList(g, group, "_id", "_id"):
            g.append(group)
    return json_util.dumps(g)


# Servizio che fornisce la lista di tutte le autorizzazioni inserite dall'utente
@post("/list_auth")
def getAllAuth():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    res = Connections.getAuth().find({"creator": query["id"]})
    list_auth = []
    for item in res:
        list_auth.append(Utils.manipulateItem(item))
    res = Connections.getAuth().find({"creator": {"$ne": query["id"]}})
    for auth_del in res:
        cal_owner = Connections.getCal().find_one({"_id": ObjectId(auth_del["calendar_id"])}, {"owner": 1, "_id": 0})["owner"]
        if cal_owner == query["id"]:
            list_auth.append(Utils.manipulateItem(auth_del))
    return json_util.dumps(list_auth)


# Servizio che permette di cancellare una auth e aggiorna le relative referenze
@post("/delete_auth")
def deleteAuth():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    myquery = {"_id": ObjectId(query['auth_id'])}
    ris = Connections.getAuth().find_one(myquery, {"calendar_id": 1, "group_id": 1})
    res = Connections.getAuth().delete_one(myquery)
    newvalues = {"$pull": {'Authorization': ris["_id"]}}
    test = Connections.getCal().find_one({"_id": ObjectId(ris["calendar_id"])})
    Connections.getCal().update_one({"_id": ObjectId(ris["calendar_id"])}, newvalues)
    if Connections.getUser().find_one({"_id": ObjectId(ris["group_id"])}) is None:
        Connections.getGroup().update_one({"_id": ObjectId(ris["group_id"])}, newvalues)
    else:
        Connections.getUser().update_one({"_id": ObjectId(ris["group_id"])}, newvalues)
    if res.deleted_count != 1:
        return "Errore nella cancellazione"
    return "Cancellazione completata con successo"

# Servizio che fornisce la lista di tutte le precondizioni inserite dall'utente
@post("/list_pre")
def getAllPre():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    res = Connections.getPrecondition().find({"creator": query["id"]})
    list_pre = []
    for item in res:
        item["group_id"] = Connections.getGroup().find_one({"_id": ObjectId(item["group_id"])}, {"_id": 0, "name": 1})["name"]
        item["calendar_id"] = Connections.getCal().find_one({"_id": ObjectId(item["calendar_id"])}, {"_id": 0, "type": 1})["type"]
        list_pre.append(item)
    return json_util.dumps(list_pre)

# Servizio che fornisce la lista di tutte le auth amministrative inserite dall'utente
@post("/list_admin_pre")
def getAllAdminPre():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    res = Connections.getAdmin_Auth().find({"creator": query["id"]})
    list_pre = []
    for item in res:
        item["user_id"] = Connections.getUser().find_one({"_id": ObjectId(item["user_id"])}, {"_id": 0, "username": 1})["username"]
        item["calendar_id"] = Connections.getCal().find_one({"_id": ObjectId(item["calendar_id"])}, {"_id": 0, "type": 1})["type"]
        list_pre.append(item)
    return json_util.dumps(list_pre)

# Servizio che fornisce la possibilità di cancellare le auth amministrative
@post("/delete_admin_pre")
def deleteAdminPre():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    myquery = {"_id": ObjectId(query['pre_id'])}
    ris = Connections.getAdmin_Auth().find_one(myquery, {"calendar_id": 1, "user_id": 1})
    res = Connections.getAdmin_Auth().delete_one(myquery)
    newvalues = {"$pull": {'Admin_auth': ris["_id"]}}
    Connections.getCal().update_one({"_id": ObjectId(ris["calendar_id"])}, newvalues)
    Connections.getUser().update_one({"_id": ObjectId(ris["user_id"])}, newvalues)
    if res.deleted_count != 1:
        return "Errore nella cancellazione"
    return "Cancellazione completata con successo"


# Servizio che fornisce la possibilità di cancellare le precondizioni temporali
@post("/delete_pre")
def deletePre():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    myquery = {"_id": ObjectId(query['pre_id'])}
    ris = Connections.getPrecondition().find_one(myquery, {"calendar_id": 1, "group_id": 1})
    res = Connections.getPrecondition().delete_one(myquery)
    newvalues = {"$pull": {'Precondition': ris["_id"]}}
    Connections.getCal().update_one({"_id": ObjectId(ris["calendar_id"])}, newvalues)
    if Connections.getUser().find_one({"_id": ObjectId(ris["group_id"])}) is None:
        Connections.getGroup().update_one({"_id": ObjectId(ris["group_id"])}, newvalues)
    else:
        Connections.getUser().update_one({"_id": ObjectId(ris["group_id"])}, newvalues)
    if res.deleted_count != 1:
        return "Errore nella cancellazione"
    return "Cancellazione completata con successo"

# Servizio che fornisce la possibilità di rimuovere un utente da un gruppo
@post("/delete_user")
def deleteUser():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    user_id = Connections.getUser().find_one({"username": query["user"]}, {"_id":1})
    if user_id is not None:
        group = Connections.getGroup().find_one({"_id": ObjectId(query["group"])}, {"_id":1})
        if group is not None:
            newvalues = {"$pull": {'User': user_id["_id"]}}
            Connections.getGroup().update_one({"_id": group["_id"]}, newvalues)
            return "Rimozione completata con successo"
        return "Gruppo inesistente"
    return "Utente inesistente"


@post("/delete_user_hier")
def deleteUserHier():
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    print(query)
    hier = Connections.getHier().find_one({"owner": query["id"]})
    existGroup = {}
    if hier is not None:
        for couple in hier["Hier"]:
            if couple["node"] == query["son"] and couple["belongsto"] == query["dad"]:
                existGroup= couple
                break

        if len(existGroup) != 0:
            print(existGroup)
            newvalues = {"$pull": {'Hier': {"node": existGroup["node"], "belongsto": existGroup["belongsto"]}}}
            Connections.getHier().update_one({"owner": query["id"]}, newvalues)
            G = HierarchyUtils.getG(query["id"])
            HierarchyUtils.save_image(G, query["id"])
            return "Esiste una coppia di questo tipo"
        else:
            print("Non esiste coppia")
            return "Nessuna coppia di questo tipo presente in gerarchia"
    return "Nessuna gerarchia presente"


# Servizio che fornisce tutti gli eventi visibili su un determinato calendario
@post("/event_vis")
def event_vis():
    event_owner_cal = []
    query = StringUtils.get_query_new(request.body.read().decode('utf-8'))
    if len(query['calendar'])==0:
        return []
    res = Connections.getCal().find_one({"owner": query["id"], "_id": ObjectId(query['calendar'])})
    # aggiungi tutti gli eventi contenuti nel calendario di cui è owner

    if res is not None:
        ris = Connections.getEvent().find({"calendar": str(res['_id'])})
        for item in ris:
            event_owner_cal.append(item)
        return json_util.dumps(event_owner_cal)

    # Se si tratta di un delegato, ritorna tutti gli eventi di quel calendario
    delegate_events = EventViewerUtils.eventsADelegateCanRead(query["id"], query['calendar'])
    if len(delegate_events) != 0:
        return json_util.dumps(delegate_events)
    # Possono esserci più auth, su più gruppi
    user_group = Utils.user_to_group(query["id"])
    events = EventViewerUtils.getVisibileEventsWithHier(query['id'], query['calendar'], "show")
    events_writable = EventViewerUtils.eventUserCanWrite(query["id"], query["calendar"])

    if len(events) != 0:
        if len(user_group) == 1:
            result = Connections.getGroup().find_one({"_id": user_group[0]}, {"Precondition": 1, "_id": 0})
            events = PreCondUtils.precond(result['Precondition'], events, query['calendar'])
        else:
            for group in user_group:
                result = Connections.getGroup().find_one({"_id": group}, {"Precondition": 1, "_id": 0})
                events = PreCondUtils.precond(result['Precondition'], events, query['calendar'])
        list = [events, events_writable]
        final = Utils.create_set_union(list)
        return json_util.dumps(final)
    else:
        return []


app.install(EnableCors())
run(host='0.0.0.0', port=12345, debug=True)
