from django.shortcuts import render
from django import forms
import requests
# import json
import dateutil.parser as du
# import dateutil.parser as du
from BeautifulSoup import BeautifulSoup, SoupStrainer

# Create your views here.
'''
Company Search
https://www.sec.gov/cgi-bin/browse-edgar?company=[QUERY]&owner=exclude&action=getcompany

CIK Search
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000819544&type=10-k&dateb=20150101&owner=exclude&count=40
'''


class EdgarRequestForm(forms.Form):
    cik = forms.CharField(max_length=30)
    filing = forms.CharField(max_length=30)
    after_date = forms.DateField(required=False)
    before_date = forms.DateField(required=False)

    def get_document_for_item(self, url):
        documents_page = requests.get(url)
        content = "No content found."
        if documents_page:
            links = BeautifulSoup(
                documents_page.content,
                parseOnlyThese=SoupStrainer('table', {'class': 'tableFile'})
            ).findAll('a')
            links = [l for l in links if '.txt' in l.text]
            if links:
                content_url = "https://www.sec.gov%s" % links[0].get('href')
                print(content_url)
                resp = requests.get(content_url)
                content = resp.content if resp else "Connection error."
        return content

    def save(self):
        cik_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany" + \
            "&CIK=%s&type=%s&dateb=%s&owner=exclude&count=40" % \
            (self.cleaned_data.get('cik'),
             self.cleaned_data.get('filing'),
             self.cleaned_data.get('before_date'))

        resp = requests.get(cik_url)
        soup = BeautifulSoup(
            resp.content,
            parseOnlyThese=SoupStrainer('table', {'class': 'tableFile2'}))

        data = []
        table = soup.find('table', attrs={'class': 'tableFile2'})
        rows = table.findAll('tr')
        for row in rows:
            cols = row.findAll('td')
            if cols:
                # get document page url
                doc_url = "https://www.sec.gov%s" % \
                    cols[1].find('a', attrs={'id': 'documentsbutton'})\
                    .get('href')
                content = self.get_document_for_item(doc_url)

                cols = [ele.text for ele in cols]

                filing_date = du.parse(cols[3].strip()).date()
                if (self.cleaned_data.get('after_date') and
                        filing_date < self.cleaned_data.get('after_date')):
                    continue

                # strip everything after closing bracket
                desc_list = cols[2].split()
                item_no = desc_list[desc_list.index('Item') + 1]
                item_no = item_no[:item_no.find(']')]

                output = {
                    'filing': cols[0].strip(),
                    'filing_date': filing_date,
                    'item_no': item_no,
                    'item_desc': 'FOO',
                    # content will be the parse, not the url
                    'content': content,
                }
                data.append(output)

        return data


def edgar(request):
    if request.method == 'POST':
        form = EdgarRequestForm(data=request.POST)
        if form.is_valid():
            resp = form.save()
        else:
            resp = "Error"
    else:
        form = EdgarRequestForm()
        resp = None

    return render(request, "base.html", {
        'form': form,
        'resp': resp,
    })
