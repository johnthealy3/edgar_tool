from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django import forms
import requests
import json
import re
import dateutil.parser as du
# import dateutil.parser as du
from BeautifulSoup import BeautifulSoup, SoupStrainer

'''
Company Search
https://www.sec.gov/cgi-bin/browse-edgar?company=[QUERY]&owner=exclude&action=getcompany

CIK Search
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000819544&type=10-k&dateb=20150101&owner=exclude&count=40
'''


class EdgarCompanySearchForm(forms.Form):
    company = forms.CharField(max_length=255)

    def save(self):

        company_search_url = "https://www.sec.gov/cgi-bin/browse-edgar?" + \
            "company=%s&owner=exclude&action=getcompany" % self.cleaned_data.get('company')

        # It turns out this page uses very similar markup to the edgar request.
        resp = requests.get(company_search_url)
        soup = BeautifulSoup(
            resp.content,
            parseOnlyThese=SoupStrainer('table', {'class': 'tableFile2'}))

        data = []
        table = soup.find('table', attrs={'class': 'tableFile2'})
        rows = table.findAll('tr')
        for row in rows:
            cols = row.findAll('td')
            if cols:
                cols = [ele.text for ele in cols]

                output = {
                    'cik': cols[0].strip(),
                    'company_name': cols[1],
                }
                data.append(output)

        return data


class EdgarRequestForm(forms.Form):
    cik = forms.CharField(max_length=30)
    filing = forms.CharField(max_length=30, required=False)
    after_date = forms.DateField(required=False)
    before_date = forms.DateField(required=False)
    item_no = forms.CharField(max_length=30, required=False,
                              label="Item Number")
    # TODO: add item filter

    def clean_filing(self):
        data = self.cleaned_data['filing']
        return data.upper()

    def get_document_for_item(self, url, doc_type):
        documents_page = requests.get(url)
        content = "No content found."
        if documents_page:

            table = BeautifulSoup(
                documents_page.content,
                parseOnlyThese=SoupStrainer('table', {'class': 'tableFile'})
            )
            html_link = None
            # If there is an HTML document where "type" matches
            # the type from the query, that's the formatted version.
            # We scrape this for the appropriate item number and save that
            # to content.
            rows = table.findAll('tr')
            for row in rows:
                cols = row.findAll('td')
                if cols and cols[3].text == doc_type:
                    html_link = cols[2].find('a').get('href')
                    content = html_link

            if not html_link:
                # This is the fallback. If there is only a text link,
                # return it's url.
                text_links = [l for l in table.findAll('a') if '.txt' in l.text]
                if text_links:
                    content = text_links[0].get('href')

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

                cols = [ele.text for ele in cols]
                filing = cols[0].strip()
                filing_date = du.parse(cols[3].strip()).date()

                if (self.cleaned_data.get('after_date') and
                        filing_date < self.cleaned_data.get('after_date')):
                    continue

                # parse out a list of item numbers from description
                desc_list = [c.lower().replace(']', '').replace(
                             'acc-no:', '').replace(',', '')
                             for c in cols[2].split()]
                item_no = []
                try:
                    item_no.append(desc_list[desc_list.index('item') + 1])
                except ValueError:
                    try:
                        # look for multiples. this should probably be a regex.
                        idx = desc_list.index('items') + 1
                        item_no.append(desc_list[idx])
                        for item in desc_list[idx + 1:]:
                            try:
                                float(item)
                                item_no.append(item)
                            except ValueError:
                                # item is not numeric
                                if item.strip().lower() != 'and':
                                    break

                    except ValueError:
                        # 'Item' was not present in the description
                        pass

                if (self.cleaned_data.get('item_no') and
                        self.cleaned_data.get('item_no') not in item_no):
                    continue

                content = self.get_document_for_item(doc_url, filing)

                output = {
                    'filing': filing,
                    'filing_date': filing_date,
                    'item_no': ', '.join([i for i in item_no]),
                    'item_desc': 'FOO',
                    'content': content,
                }
                data.append(output)

        return data


def edgar(request):
    company_search_form = EdgarCompanySearchForm()
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
        'company_search_form': company_search_form,
    })


@require_http_methods(["POST"])
def ajax_company_search(request):
    form = EdgarCompanySearchForm(request.POST)
    if form.is_valid():
        data = form.save()
        message = "Success"
    else:
        data = None
        message = "Error"

    html = render_to_string('company_search.html', {
        'data': data,
    })

    return HttpResponse(json.dumps({
        'html': html,
        'message': message,
    }), content_type='application/json')


@require_http_methods(["POST"])
@csrf_exempt
def ajax_sec_url(request):
    url = request.GET.get('url')
    items = request.GET.get('items')
    if items:
        items = [i.replace('.', '') for i in items.split(',')]

    if url:
        resp = requests.get("https://www.sec.gov%s" % url)
        if resp:
            if items:
                print(items)
                '''
                Going to attempt to do this as cases first rather than
                by reading the text directly.

                Case 1: Bold tags

                find "<b>Item %s.</b>" % item_no
                contents of <b> within next <td> is description

                all markup after this table and before the next <hr />
                is what we want to grab
                '''
                soup = BeautifulSoup(resp.content)
                bolds = soup.findAll('b')
                html = ''
                for b in bolds:
                    if 'Item&nbsp;' in b.text:
                        item_no = b.text.replace('Item&nbsp;', '').replace('.', '')
                        if item_no in items:
                            # this is one of our items. the next <b> is description
                            # going to not worry about this for now, as we should
                            # just store the descriptions in a lookup table
                            html += repr(b) + ': '
                            html += repr(b.findNext('b'))

                            table = b.findParents('table')
                            if table:
                                table = table[0]
                            # all markup after this table and before the
                            # next <hr /> is what we want to grab
                            # this doesn't seem to work
                            for h in table.findAllNext():
                                if h.name == 'hr':
                                    break
                                if h.name in ('p', 'div'):
                                    html += '<p>' + h.text + '</p>'
                if not html:
                    '''
                    Case 2: all divs

                    Get all the divs and the text inside. Add to the HTML output
                    all text inside all divs UNTIL the following:
                    - another item number
                    - SIGNATURE
                    '''
                    divs = soup.findAll('div')
                    for d in divs:
                        if d.text.startswith('Item'):
                            item_no = re.findall('\d+', d.text.replace('.', ''))[0]
                            if item_no in items:
                                html += '<b>' + d.text + '</b>'
                                last_text = d.text.strip()
                                for h in d.findAllNext():
                                    if h.text.strip() == last_text:
                                        continue
                                    if (h.text.startswith('Item') or
                                            h.text.startswith('SIGNATURE')):
                                        break
                                    html += '<p>' + h.text.strip() + '</p>'
                                    last_text = h.text.strip()

            else:
                html = resp.content
            message = "Success"
        else:
            html = None
            message = "Error"
    else:
        html = None
        message = "Needs a valid url."

    return HttpResponse(json.dumps({
        'html': html,
        'message': message,
    }), content_type='application/json')
