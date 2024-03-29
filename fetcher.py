import urllib3
import json
from collections import defaultdict
import time
from flask import Flask, abort
from valghtml.templates import HTML
from datetime import datetime
import math
import dateutil.parser as dp
from threading import Thread
import argparse

app = Flask(__name__)

BASE_URL = "https://valgresultater.no/api"
http = urllib3.PoolManager()

resultDict = {}

def createRecursivedefaultDict():
    return defaultdict(createRecursivedefaultDict)

class Results:
    def __init__(self, results):
        self.id = results["id"]
        self.time = results["tidspunkt"]
        self.timestamp = self.time["rapportGenerert"]
        self.mandater = results["mandater"]["antall"]
        self.stemmer = results["stemmer"]
        self.opptalt = results["opptalt"]
        self.partier = results["partier"]
        self.children = results["_links"]["related"]
        self.childrenUpdate = {x["href"]: x["rapportGenerert"] for x in self.children }
        self.link = results["_links"]["self"]["href"]
        self.up = results["_links"]["up"]["href"]
        self.rawLinks = results["_links"]
        #resultDict[self.link] = self

    @staticmethod
    def downloadResult(path, retries=1):
        try:
            response = http.request("GET", BASE_URL+path)
            resultDict[path] = Results(json.loads(response.data))
            print("loaded successfully: " + path)
            return resultDict[path]
        except Exception as e:
            print("ERROR loading results for " + path)
            print(e)
            if (retries > 0):
                time.sleep(1)
                Results.downloadResult(path, retries-1)

    def parent(self):
        if (len(self.up) == 5):
            return None
        try:
            return resultDict[self.up]
        except KeyError:
            return Results.downloadResult(self.up)

    def update(self, child=None, ts=None):
        isUpdated = True
        parent = self.parent()
        current = self
        if (parent):
            isUpdated = parent.update(self.link, self.timestamp)
        if not isUpdated:
            current = Results.downloadResult(self.link)
        return child == None or current.childrenUpdate[child] == ts

    def resultater(self):
        print(self.partier)
        return self.partier

    def resultatListe(self):
        opptalt = {}
        ppabsolutt = {}
        ppendring = {}
        prognoseabsolutt = {}
        prognoseendring = {}
        ppprognoseEllerOpptalt = {}
        underSperregrensa = {}
        mabsolutt = {}
        direktemandater = {}
        mendring = {}
        utjevning = {}
        stemmeantall = {}
        nesteMandat = {}
        sisteMandat = {}
        nesteStemmer = {}
        sisteStemmer = {}
        harPersoner = False
        sperregrense = math.ceil(self.stemmer["total"]/25)
        globalSisteKvotient = 10000000
        globalNesteKvotient = 0
        ikkeblanke = self.stemmer["total"]

        prognose = False
        for parti in self.partier:
            kategori = parti["id"]["partikategori"]
            kode = parti["id"]["partikode"]
            resultat = parti["stemmer"]["resultat"]
            prosentresultat = resultat["prosent"] or -1
            if kode == "BLANKE":
                ikkeblanke -= resultat["antall"]["total"]
            if kategori != 1 and prosentresultat < 1:
                continue
            opptalt[kode] = self.opptalt["forelopig"]
            ppabsolutt[kode] = prosentresultat
            ppprognoseEllerOpptalt[kode] = prosentresultat or 0
            ppendring[kode] = resultat["endring"]["samme"] or 0
            prognoseendring[kode] = prognoseabsolutt[kode] = mabsolutt[kode] = mendring[kode] = direktemandater[kode] = -1
            if prognose:
                prognoseabsolutt[kode] = parti["stemmer"]["prognose"]["prosent"]
                ppprognoseEllerOpptalt[kode] = prognoseabsolutt[kode] or 0
                prognoseendring[kode] = parti["stemmer"]["prognose"]["endring"]["samme"]
            underSperregrensa[kode] = self.mandater == 169 and (ppprognoseEllerOpptalt[kode] < 4)
            stemmeantall[kode] = resultat["antall"]["total"]
            mandater = None
            try:
                if prognose:
                    mandater = parti["mandater"]["prognose"]
                else:
                    mandater = parti["mandater"]["resultat"]
            except KeyError:
                pass
            utjevning[kode] = 0
            if mandater:
                utjevning[kode] = mandater["utjevningAntall"]
                mabsolutt[kode] = mandater["antall"]
                direktemandater[kode] = mandater["antall"]
                if self.mandater != 169:
                    direktemandater[kode] -= utjevning[kode]
                mendring[kode] = mandater["endring"]

                grunnlag = stemmeantall[kode]
                if prognose:
                    grunnlag = ppprognoseEllerOpptalt[kode]

                if kode != "Andre" and not underSperregrensa[kode] and direktemandater[kode] > 0:
                    globalNesteKvotient = max(globalNesteKvotient, grunnlag / max(1.4, direktemandater[kode] * 2 + 1))
                    globalSisteKvotient = min(globalSisteKvotient, grunnlag / max(1.4, direktemandater[kode] * 2 - 1))
                nesteMandat[kode] = sisteMandat[kode] = ""
                try:
                    if len(mandater["nesteKandidater"])>0:
                        nesteMandat[kode] = mandater["nesteKandidater"][0]["navn"]
                        harPersoner = True
                except KeyError:
                    pass
                try:
                    if len(mandater["representanter"])>0:
                        sisteMandat[kode] = mandater["representanter"][-1]["navn"]
                        harPersoner = True
                        if mandater["representanter"][-1]["utjevningsmandat"]:
                            sisteMandat[kode] += " (u)"
                except KeyError:
                    pass
        for kode, antall in direktemandater.items():
            if underSperregrensa[kode]:
                if stemmeantall[kode] == 0:
                    nesteStemmer[kode] = (4, sperregrense)
                else:
                    nesteStemmer[kode] = (4-ppprognoseEllerOpptalt[kode], stemmeantall[kode]/ppprognoseEllerOpptalt[kode]*4-stemmeantall[kode])
            else:
                if prognose:
                    x = globalSisteKvotient*max(1.4, antall*2+1.)-ppprognoseEllerOpptalt[kode]
                    nesteStemmer[kode] = (x, x*ikkeblanke/100)
                else:
                    x = globalSisteKvotient * max(1.4, antall * 2 + 1.) - stemmeantall[kode]
                    nesteStemmer[kode] = (x/max(1,ikkeblanke)*100, x)
            sisteStemmer[kode] = (-1, -1)
            if antall > 0 and not underSperregrensa[kode]:
                if prognose:
                    x = -(globalNesteKvotient*max(1.4, antall*2-1.)-ppprognoseEllerOpptalt[kode])
                    sisteStemmer[kode] = (x, x*ikkeblanke/100)
                else:
                    x = -(globalNesteKvotient*max(1.4, antall*2-1.) - stemmeantall[kode])
                    sisteStemmer[kode] = (x/max(1,ikkeblanke)*100, x)
        return {
            "Oppslutning %": ppabsolutt,
            "Endring %": ppendring,
            "Prognose %": prognoseabsolutt,
            "Prognose endring %": prognoseendring,
            "Mandater totalt": self.mandater,
            "Mandater": mabsolutt,
            "Mandater endring": mendring,
            "Utjevning": utjevning,
            "Opptalt": self.opptalt,
            "Stemmeantall": stemmeantall,
            "Stemmer for neste mandat": nesteStemmer,
            "Stemmer for siste mandat": sisteStemmer,
            "Sistemandat": sisteMandat,
            "Nestemandat": nesteMandat,
            "sisteKvotient": globalSisteKvotient,
            "nesteKvotient": globalNesteKvotient,
            "harPersoner" : harPersoner,
            "opptalt": opptalt
        }

    def getLink(self):
        return '''
        <table border="1" style="float: left">
        <tr><th>Navigering</th><th>Alder</th><th>Opptalt</th></tr>
        {up}
        {self}
        {children}
        '''.format(up=self.makeLink(self.rawLinks["up"]), self=self.makeLink(self.rawLinks["self"]),
                   children="".join([self.makeLink(link) for link in self.rawLinks["related"]]))

    def makeLink(self, link):
        navn = link["navn"]
        selv = False
        if not navn:
            return ""
        if navn == self.id["navn"]:
            navn = "<b>{boldname}</b>".format(boldname=navn)
            selv = True
        linkTime = ""
        opptalt = ""
        try:
            linkTime = link["rapportGenerert"]
            opptalt = link["forelopig"]
        except KeyError:
            pass
        return '''
        <tr><td><a href="/results{url}">{name}</a></td><td>{time}</td><td>{opptalt}</td></tr>
        '''.format(url=link["href"],
                   name=navn,
                   time=str(toTimeAgo(self.timestamp if selv else linkTime)),
                   opptalt=opptalt)

    @staticmethod
    def farge(kode):
        if kode=="A":
            return "FF9999"
        if kode=="SV":
            return "FF6666"
        if kode=="RØDT":
            return "FF0000"
        if kode=="SP":
            return "CC9900"
        if kode=="KRF":
            return "FFFF00"
        if kode.startswith("MDG"):
            return "00FF00"
        if kode=="V":
            return "00CCCC"
        if kode=="H":
            return "0066FF"
        if kode=="FRP":
            return "663300"
        return "999999"

    def resultatTabellHTML(self, liste):
        d=liste["Stemmeantall"]
        partier = [k for k in sorted(d, key=d.get, reverse=True)]
        harmandater = self.mandater > 0
        mandatheader = "<th>Mandater</th><th>Endring</th>" if harmandater else ""
        kapreheader = "<th>Kapre mandat</th><th>Miste mandat</th>" if harmandater else ""
        personheader = "<th>Siste mandat</th><th>Neste mandat</th>" if liste["harPersoner"] else ""
        return '''
        <table border="1" style="float: left">
        <tr>
        <th>Parti</th><th>Resultat</th><th>Endring</th><th>Prognose</th><th>Endring</th><th>Opptalt</th>{mandatheader}<th>Stemmer</th>{kapreheader}{personheader}
        </tr>
        {rows}
        </table>
        '''.format(mandatheader = mandatheader, kapreheader = kapreheader, personheader = personheader,
                   rows = "".join([Results.resultatRadHTML(liste, parti, harmandater, liste["harPersoner"]) for parti in partier]))

    @staticmethod
    def round(number):
        try:
            return round(number, 3)
        except:
            return number

    @staticmethod
    def resultatRadHTML(liste, kode, harmandater, harpersoner):
        utjevning = ""
        if liste["Utjevning"][kode] > 0:
            utjevning = " (u: %d)" % liste["Utjevning"][kode]
        pp, abs = liste["Stemmer for neste mandat"][kode]
        neste = "(%s, %d)" % (Results.round(pp), math.ceil(abs))
        pp, abs = liste["Stemmer for siste mandat"][kode]
        siste = "(%s, %d)" % (Results.round(pp), math.ceil(abs))
        return '''
        <tr>
        <td bgColor="#{farge}">{kode}</td><td>{resultat}</td><td>{rendring}</td><td>{prognose}</td><td>{pendring}</td><td>{opptalt}</td>{mandater}<td>{stemmer}
        {nestesiste}{nestesisteperson}
        <tr>
        '''.format(farge=Results.farge(kode),
                   kode=kode,
                   resultat=Results.round(liste["Oppslutning %"][kode]),
                   rendring=Results.round(liste["Endring %"][kode]),
                   prognose=Results.round(liste["Prognose %"][kode]),
                   pendring=Results.round(liste["Prognose endring %"][kode]),
                   opptalt=Results.round(liste["opptalt"][kode]),
                   mandater = "<td>%s</td><td>%s</td>" % (str(liste["Mandater"][kode]) + utjevning,liste["Mandater endring"][kode]) if harmandater else "",
                   stemmer=liste["Stemmeantall"][kode],
                   nestesiste = "<td>%s</td><td>%s</td>" % (neste, siste) if harmandater else "",
                   nestesisteperson = "<td>%s</td><td>%s</td>" % (
                       liste["Sistemandat"][kode], liste["Nestemandat"][kode]
                   ) if harpersoner else "")


    @staticmethod
    def fetchNewest(path):
        try:
            Results.downloadResult(path)
            result = resultDict[path]
        except KeyError:
            return Results.downloadResult(path)
        result.update()
        return resultDict[path]

    @staticmethod
    def downloadTree(path, timeStamp=None, sleep=0.5, depth=3):
        if depth == 0:
            return
        current = None
        try:
            current = resultDict[path]
        except KeyError:
            current = Results.fetchNewest(path)
            timeStamp = None
        for childpath, ts in current.childrenUpdate.items():
            if timeStamp != ts:
                Results.downloadTree(childpath, ts, sleep, depth-1)
                time.sleep(sleep)
    def __str__(self):
        return f'"Name": {self.id["navn"]}, "Opptalt": {self.opptalt}, "Timestamp": {toTimeAgo(self.timestamp)}'

def toTimeAgo(inputDate):
    if not inputDate:
        return ""
    oldDate = dp.parse(inputDate)
    if not oldDate:
        return ""
    diff = datetime.now().replace(microsecond=0) - oldDate
    return diff

@app.route('/results/<int:year>/<string:type>')
def getSummary(year, type):
    path = "/{year}/{type}".format(year=year, type=type)
    result = Results.fetchNewest(path)
    if not result:
        abort(404, "Path not found: " + path)
    resultliste = result.resultatListe()
    mdgliste = {}
    for fylke in result.children:
        fylkeresult = Results.fetchNewest(fylke["href"]).resultatListe()
        nykode = "MDG "+str(fylke["navn"])
        if fylkeresult["harPersoner"] != True:
            continue
        mdgliste["harPersoner"] = True
        for key, value in fylkeresult.items():
            if isinstance(value, dict):
                if not key in mdgliste:
                    mdgliste[key] = {}
                for parti, verdi in value.items():
                    if parti == 'MDG':
                        mdgliste[key][nykode] = verdi

    return HTML.html("Opptalt: " + str(result.opptalt) + " Antall stemmer: " + str(result.stemmer) + result.getLink(),
                     str(result.resultatTabellHTML(resultliste)) +
                     (str(result.resultatTabellHTML(mdgliste)) if mdgliste else "") +
                     koalisjonsTabell(resultliste["Mandater"]))

def koalisjonsTabell(mandater):
    return createTable("Koalisjoner",["partier", "mandater", "totalt mandater"],
                         [koalisjonsRad(("MDG", "V", "H"), mandater),
                          koalisjonsRad(("MDG", "A", "SV", "RØDT"), mandater),
                          koalisjonsRad(("MDG", "A", "SV", "V"), mandater),
                          koalisjonsRad(("MDG", "A", "SV"), mandater),
                          koalisjonsRad(("MDG", "A", "SV", "SP", "RØDT", "KRF"), mandater),
                          ])
def koalisjonsRad(partier, mandater):
    try:
        return [",".join(partier), sum(mandater[parti] for parti in partier), sum(mandater.values())-(mandater.get("Andre",0))]
    except KeyError:
        return ["",""]


@app.route('/results/<int:year>/<string:type>/<path:path>')
def getResults(year, type, path):
    path = "/{year}/{type}/{path}".format(year=year, type=type, path=path)
    result = Results.fetchNewest(path)
    if not result:
        abort(404, "Path not found: " + path)
    return HTML.html("Opptalt: " + str(result.opptalt) + " Antall stemmer: " +  str(result.stemmer) + result.getLink(),
                     str(result.resultatTabellHTML(result.resultatListe())) +
                     koalisjonsTabell(result.resultatListe()["Mandater"])
                     )

@app.route('/best/<int:year>/<string:type>')
def getBest(year, type):
    path = "/{year}/{type}".format(year=year, type=type)
    bestfylke = []
    bestkommune = []
    bestbydel = []
    bestall = []
    for (resultpath, result) in resultDict.items():
        if not resultpath.startswith(path):
            continue
        mdg = None
        try:
            for parti in result.partier:
                if parti["id"]["partikode"] == "MDG":
                    mdg = parti
        except:
            pass
        if mdg:
            try:
                pp = mdg["stemmer"]["resultat"]["prosent"]
                endring = mdg["stemmer"]["resultat"]["endring"]["samme"]
                try:
                    pp = mdg["stemmer"]["prognose"]["prosent"]
                    endring = mdg["stemmer"]["prognose"]["endring"]["samme"]
                except:
                    pass
                if not pp:
                    continue
                if not endring:
                    endring = -100
                if result.id["nivaa"] == "fylke":
                    bestfylke.append(['<a href="/results{url}">{name}</a>'.format(url=result.link, name=result.id["navn"]),
                                pp, endring])
                if result.id["nivaa"] == "kommune":
                    bestkommune.append(['<a href="/results{url}">{name}</a>'.format(url=result.link, name=result.id["navn"]),
                                pp, endring])
                if result.id["nivaa"] == "bydel":
                    bestbydel.append(
                        ['<a href="/results{url}">{name}</a>'.format(url=result.link, name=result.id["navn"]),
                         pp, endring])
                bestall.append(
                        ['<a href="/results{url}">{name}</a>'.format(url=result.link, name=result.id["navn"]),
                         pp, endring])
            except:
                pass
    bestkommuneabsolutt = sorted(bestkommune, key=lambda x:x[1], reverse=True)[0:40]
    bestkommuneendring = sorted(bestkommune, key=lambda x:x[2], reverse=True)[0:40]
    bestfylkeabsolutt = sorted(bestfylke, key=lambda x:x[1], reverse=True)[0:20]
    bestfylkeendring = sorted(bestfylke, key=lambda x:x[2], reverse=True)[0:20]
    bestbydelabsolutt = sorted(bestbydel, key=lambda x:x[1], reverse=True)[0:20]
    bestbydelendring = sorted(bestbydel, key=lambda x:x[2], reverse=True)[0:20]
    bestallabsolutt = sorted(bestall, key=lambda x:x[1], reverse=True)
    bestallendring = sorted(bestall, key=lambda x:x[2], reverse=True)
    return HTML.html(createTable("Beste kommuner",["navn", "oppslutning", "endring"], bestkommuneabsolutt)+
                     createTable("Best endring kommuner",["navn", "oppslutning", "endring"], bestkommuneendring),
                     createTable("Beste fylker",["navn", "oppslutning", "endring"], bestfylkeabsolutt) +
                     createTable("Best endring fylker", ["navn", "oppslutning", "endring"], bestfylkeendring) +
                     createTable("Beste bydeler", ["navn", "oppslutning", "endring"], bestbydelabsolutt) +
                     createTable("Best endring bydeler", ["navn", "oppslutning", "endring"], bestbydelendring)+
                     createTable("Beste totalt", ["navn", "oppslutning", "endring"], bestallabsolutt) +
                     createTable("Best endring totalt", ["navn", "oppslutning", "endring"], bestallendring)
                     )

def createTable(title, headers, elements):
    return '''
    <table border="1" style="float: left">
    <tr><th colspan="{n}">{title}</th></tr>
    <tr><th>{headerlist}</th></tr>
    <tr><td>{elementlist}</td></tr></table>
    '''.format(n=len(headers), title=title,
               headerlist="</th><th>".join(headers),
               elementlist="</td></tr><tr><td>".join(
                   ["</td><td>".join([str(y) for y in x]) for x in elements]
               ))

@app.route("/matias")
def matiasLinks():
    codes = ["11", "11/1106", "11/1149", "11/1109", "11/1103", "54", "54/5401", "54/5405",
             "18", "18/1804", "18/1871", "18/1833", "18/1870"]
    links = ""
    for code in codes:
        try:
            result = Results.fetchNewest("/2019/ko/" + code)
            links+=(result.makeLink(result.rawLinks["self"]))
        except:
            pass
    return "<table>"+links+"</table>"

@app.route("/")
def getRoot():
    return getSummary(2021, "st")

def updateRoot():
    Results.downloadResult("/2021/st")
    Results.downloadResult("/2017/st")
    Results.downloadResult("/2019/ko")
    Results.downloadResult("/2019/fy")
    while True:
        Results.downloadResult("/2021/st")
        time.sleep(5)

def updateTree(depth):
    Results.downloadTree("/2023/ko", depth=2)
    Results.downloadTree("/2023/fy", depth=2)
    while True:
        Results.downloadTree("/2023/ko", depth=1, sleep=1)
        Results.downloadTree("/2023/fy", depth=1, sleep=1)
        time.sleep(5)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Presenter data fra valg-apiet.')
    parser.add_argument('--port', dest='port', type=int, default=1337)
    parser.add_argument('--depth', dest='depth', type=int, default=2)
    args = parser.parse_args()
    #t1 = Thread(target=updateRoot).start()
    t2 = Thread(target=updateTree, args=(args.depth,)).start()
    app.run(host="0.0.0.0", port=args.port)
