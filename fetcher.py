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
        self.opptalt = results["opptalt"]
        self.prognose = results["prognose"]
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
        ppabsolutt = {}
        ppendring = {}
        prognoseabsolutt = {}
        prognoseendring = {}
        mabsolutt = {}
        mendring = {}
        stemmeantall = {}
        nesteMandat = {}
        sisteMandat = {}
        nesteStemmer = {}
        sisteStemmer = {}
        globalSisteMandat = 0
        globalNesteMandat = 0
        for parti in self.partier:
            kategori = parti["id"]["partikategori"]
            kode = parti["id"]["partikode"]
            resultat = parti["stemmer"]["resultat"]
            prosentresultat = resultat["prosent"] or -1
            if kategori != 1 and prosentresultat < 1:
                continue
            ppabsolutt[kode] = prosentresultat
            ppendring[kode] = resultat["endring"]["samme"] or 0
            prognoseendring[kode] = prognoseabsolutt[kode] = mabsolutt[kode] = mendring[kode] = -1
            if self.prognose["beregnet"]:
                prognoseabsolutt[kode] = parti["stemmer"]["prognose"]["prosent"]
                prognoseendring[kode] = parti["stemmer"]["prognose"]["endring"]["samme"]
            stemmeantall[kode] = resultat["antall"]["total"]
            mandater = None
            try:
                mandater = parti["mandater"]["resultat"]
            except KeyError:
                pass
            if mandater:
                mabsolutt[kode] = mandater["antall"]
                mendring[kode] = mandater["endring"]
                try:
                    siste = mandater["sisteMandat"]
                    neste = mandater["nesteMandat"]
                    if siste["mandatrang"] == self.mandater:
                        globalSisteMandat = stemmeantall[kode]/max(1.4, mabsolutt[kode]*2-1.)
                    if neste["mandatrang"] == self.mandater+1:
                        globalNesteMandat = stemmeantall[kode]/max(1.4, mabsolutt[kode]*2+1.)
                    nesteMandat[kode] = neste
                    sisteMandat[kode] = siste
                except KeyError:
                    pass
        for kode, antall in mabsolutt.items():
            nesteStemmer[kode] = math.ceil(globalSisteMandat*max(1.4, antall*2+1.)-stemmeantall[kode])
            sisteStemmer[kode] = -1
            if antall > 0:
                sisteStemmer[kode] = -math.ceil(globalNesteMandat*max(1.4, antall*2-1.)-stemmeantall[kode])
        return {
            "Oppslutning %": ppabsolutt,
            "Endring %": ppendring,
            "Prognose %": prognoseabsolutt,
            "Prognose endring %": prognoseendring,
            "Mandater totalt": self.mandater,
            "Mandater": mabsolutt,
            "Mandater endring": mendring,
            "Opptalt": self.opptalt,
            "Stemmeantall": stemmeantall,
            "Stemmer for neste mandat": nesteStemmer,
            "Stemmer for siste mandat": sisteStemmer,
            "sisteKvotient": globalSisteMandat,
            "nesteKvotient": globalNesteMandat
        }
    def getLink(self):
        return '''
        <table border="1" style="float: left">
        <tr><th>Navigering</th><th>Alder</th></tr>
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
        try:
            linkTime = link["rapportGenerert"]
        except KeyError:
            pass
        return '''
        <tr><td><a href="/results{url}">{name}</a></td><td>{time}</td></tr>
        '''.format(url=link["href"], name=navn, time=str(toTimeAgo(self.timestamp if selv else linkTime)))

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
        if kode=="MDG":
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
        return '''
        <table border="1" style="float: left">
        <tr>
        <th>Parti</th><th>Resultat</th><th>Endring</th><th>Prognose</th><th>Endring</th><th>Mandater</th><th>Endring</th><th>Stemmer</th><th>Kapre mandat</th><th>Miste mandat</th>
        </tr>
        {rows}
        </table>
        '''.format(rows = "".join([Results.resultatRadHTML(liste, parti) for parti in partier]))

    @staticmethod
    def round(number):
        try:
            return round(number, 2)
        except:
            return number

    @staticmethod
    def resultatRadHTML(liste, kode):
        return '''
        <tr>
        <td bgColor="#{farge}">{kode}</td><td>{resultat}</td><td>{rendring}</td><td>{prognose}</td><td>{pendring}</td><td>{mandater}</td><td>{mendring}</td><td>{stemmer}
        </td><td>{neste}</td><td>{siste}</td>
        <tr>
        '''.format(farge=Results.farge(kode), kode=kode, resultat=Results.round(liste["Oppslutning %"][kode]), rendring=Results.round(liste["Endring %"][kode]),
                   prognose=Results.round(liste["Prognose %"][kode]),pendring=Results.round(liste["Prognose endring %"][kode]),
                   mandater=liste["Mandater"][kode], mendring=liste["Mandater endring"][kode],
                   stemmer=liste["Stemmeantall"][kode], neste=liste["Stemmer for neste mandat"][kode], siste=liste["Stemmer for siste mandat"][kode])


    @staticmethod
    def fetchNewest(path):
        try:
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
    return HTML.html("Opptalt: " + str(result.opptalt) + result.getLink(), str(result.resultatTabellHTML(result.resultatListe())))

@app.route('/results/<int:year>/<string:type>/<path:path>')
def getResults(year, type, path):
    path = "/{year}/{type}/{path}".format(year=year, type=type, path=path)
    result = Results.fetchNewest(path)
    if not result:
        abort(404, "Path not found: " + path)
    return HTML.html("Opptalt: " + str(result.opptalt) + result.getLink(), str(result.resultatTabellHTML(result.resultatListe())))

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
    while True:
        Results.downloadResult("/2017/st")
        Results.downloadResult("/2019/ko")
        Results.downloadResult("/2019/fy")
        Results.downloadResult("/2021/st")
        time.sleep(50)

def createTree():
    while True:
        Results.downloadTree("/2019/ko", depth=2, sleep=0)
        Results.downloadTree("/2019/fy", depth=2)
        #Results.downloadTree("/2015/ko", depth=2)
        #Results.downloadTree("/2015/fy", depth=2)
        time.sleep(5)

if __name__ == "__main__":
    t1 = Thread(target=updateRoot).start()
    t2 = Thread(target=createTree).start()
    app.run(host="0.0.0.0", port=1337)
