import urllib3
import json
from collections import defaultdict
import time
from flask import Flask, abort
from valghtml.templates import HTML
from datetime import datetime
import math
import dateutil.parser as dp

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
    def resultatRadHTML(liste, kode):
        return '''
        <tr>
        <td bgColor="#{farge}">{kode}</td><td>{resultat}</td><td>{rendring}</td><td>{prognose}</td><td>{pendring}</td><td>{mandater}</td><td>{mendring}</td><td>{stemmer}
        </td><td>{neste}</td><td>{siste}</td>
        <tr>
        '''.format(farge=Results.farge(kode), kode=kode, resultat=round(liste["Oppslutning %"][kode],2), rendring=round(liste["Endring %"][kode],2),
                   prognose=round(liste["Prognose %"][kode],2),pendring=round(liste["Prognose endring %"][kode],2),
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
    def downloadTree(path, timeStamp=None, sleep=0.1, depth=3):
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
                #time.sleep(sleep)
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
    return HTML.html(result.getLink(), str(result.resultatTabellHTML(result.resultatListe())))

@app.route('/results/<int:year>/<string:type>/<path:path>')
def getResults(year, type, path):
    path = "/{year}/{type}/{path}".format(year=year, type=type, path=path)
    result = Results.fetchNewest(path)
    if not result:
        abort(404, "Path not found: " + path)
    return HTML.html(result.getLink(), str(result.resultatTabellHTML(result.resultatListe())))

if __name__ == "__main__":
    app.run()

#Results.downloadResult("/2019/ko")
#Results.downloadTree("/2019/ko", depth=1)
#oslo = Results.fetchNewest("/2015/ko/03")
#print(oslo.resultater())
#print(Results.fetchNewest("/2019/ko/03"))
#print(Results.fetchNewest("/2019/ko/11/1101"))
#print(Results.fetchNewest("/2019/ko/11/1101"))
