
class HTML:
    @staticmethod
    def html(links, content):
        return '''
        <html>
        <head>
        <meta http-equiv="refresh" content="5">
        </head>
        <body>
        {header}
        <hr>
        {links}
        <hr>
        {content}
        <hr>
        {footer}
        </body>
        </html>
        '''.format(header=HTML.header(),links=links, content=content, footer=HTML.footer())

    @staticmethod
    def header():
        return '''
        <h1>Valgresultater MDG</h1>
        <a href="/results/2015/ko">Kommune 2015</a>
        <a href="/results/2015/fy">Fylke 2015</a>
        <a href="/results/2017/st">Storting 2017</a>
        <a href="/results/2019/ko">Kommune 2019</a>
        <a href="/results/2019/fy">Fylke 2019</a>
        <a href="/results/2021/st">Storting 2021</a>
        <a href="/best/2019/ko">Best i kommunevalget</a>
        <a href="/best/2019/fy">Best i fylkestingsvalget</a>
        '''

    @staticmethod
    def footer():
        return '''
        Created by Matias Holte (matias.holte på gmail.com) using valgresultater.no/api
        '''