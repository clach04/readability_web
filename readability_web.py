#!/usr/bin/env python
# -*- coding: us-ascii -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
#
# Postlight (Mercury) Parser Web API access to Python implementation of Readability
# Copyright (C) 2023 Chris Clark - clach04

import json
import logging
import os
try:
    import hashlib
    #from hashlib import md5
    md5 = hashlib.md5
except ImportError:
    # pre 2.6/2.5
    from md5 import new as md5
import sys
import urllib
try:
    # Py2
    from urllib import quote_plus, urlretrieve  #TODO is this in urllib2?
    from urllib2 import urlopen, Request, HTTPError
except ImportError:
    # Py3
    from urllib.error import HTTPError
    from urllib.request import urlopen, urlretrieve, Request
    from urllib.parse import quote_plus

import readability
from readability import Document  # https://github.com/buriy/python-readability/   pip install readability-lxml

try:
    import trafilatura  # readability alternative, note additional module htmldate available for date processing - pip install  requests trafilatura
    """
    https://github.com/adbar/trafilatura

    pip install  requests trafilatura

    Successfully installed certifi-2023.5.7 charset-normalizer-3.2.0 courlan-0.9.3 dateparser-1.1.8 htmldate-1.4.3 idna-3.4 justext-3.0.0 langcodes-3.3.0 lxml-4.9.3 p
    python-dateutil-2.8.2 pytz-2023.3 regex-2023.6.3 requests-2.31.0 six-1.16.0 tld-0.13 trafilatura-1.6.1 tzdata-2023.3 tzlocal-5.0.1 urllib3-2.0.3
    """
except ImportError:
    # Py2 not supported
    trafilatura = None


from markdownify import markdownify  # https://github.com/matthewwithanm/python-markdownify  pip install markdownify
# https://github.com/matthewwithanm/python-markdownify  pip install markdownify
# Successfully installed beautifulsoup4-4.12.2 markdownify-0.11.6 soupsieve-2.4.1


log = logging.getLogger("w2d")
log.setLevel(logging.DEBUG)
disable_logging = False
#disable_logging = True
if disable_logging:
    log.setLevel(logging.NOTSET)  # only logs; WARNING, ERROR, CRITICAL

ch = logging.StreamHandler()  # use stdio

formatter = logging.Formatter("logging %(process)d %(thread)d %(asctime)s - %(filename)s:%(lineno)d %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
log.addHandler(ch)


def urllib_get_url(url, headers=None):
    """
    @url - web address/url (string)
    @headers - dictionary - optional
    """
    log.debug('get_url=%r', url)
    #log.debug('headers=%r', headers)
    response = None
    try:
        if headers:
            request = Request(url, headers=headers)
        else:
            request = Request(url)  # may not be needed
        response = urlopen(request)
        url = response.geturl()  # may have changed in case of redirect
        code = response.getcode()
        #log("getURL [{}] response code:{}".format(url, code))
        result = response.read()
        return result
    finally:
        if response != None:
            response.close()

def safe_mkdir(newdir):
    result_dir = os.path.abspath(newdir)
    try:
        os.makedirs(result_dir)
    except OSError as info:
        if info.errno == 17 and os.path.isdir(result_dir):
            pass
        else:
            raise

cache_dir = os.environ.get('CACHE_DIR', 'scrape_cache')
safe_mkdir(cache_dir)

def hash_url(url):
    m = md5()
    m.update(url.encode('utf-8'))
    return m.hexdigest()

FORCE_GET_URLS = os.environ.get('CACHE_DISABLE', False)
if FORCE_GET_URLS:
    FORCE_GET_URLS = True
CACHE_URL_GET = not FORCE_GET_URLS

def get_url(url, filename=None, force=FORCE_GET_URLS, cache=True, hash_func=hash_url):
    """Get a url, optionally with caching
    TODO get headers, use last modified date (save to disk file as meta data), return it (and other metadata) along with page content
    """
    #filename = filename or 'tmp_file.html'
    filename = filename or os.path.join(cache_dir, hash_func(url))
    ## cache it
    if force or not os.path.exists(filename):
        log.debug('getting web page %r', url)
        # TODO grab header information
        # TODO error reporting?

        use_requests = False
        if use_requests:
            response = requests.get(url)
            page = response.text.encode('utf8')  # FIXME revisit this - cache encoding
        else:
            # headers to emulate Firefox - actual headers from real browser
            headers = {
                #'HTTP_HOST': 'localhost:8000',
                'HTTP_USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
                'HTTP_ACCEPT': '*/*',
                'HTTP_ACCEPT_LANGUAGE': 'en-US,en;q=0.5',
                'HTTP_ACCEPT_ENCODING': 'gzip, deflate, br',
                'HTTP_SERVICE_WORKER': 'script',
                'HTTP_CONNECTION': 'keep-alive',
                'HTTP_COOKIE': 'js=y',  # could be problematic...
                'HTTP_SEC_FETCH_DEST': 'serviceworker',
                'HTTP_SEC_FETCH_MODE': 'same-origin',
                'HTTP_SEC_FETCH_SITE': 'same-origin',
                'HTTP_PRAGMA': 'no-cache',
                'HTTP_CACHE_CONTROL': 'no-cache'
            }

            page = urllib_get_url(url, headers=headers)

        if cache:
            f = open(filename, 'wb')
            f.write(page)
            f.close()
            # initial index - needs reworking - if filename passed in, hash is not used
            index_filename = os.path.join(os.path.dirname(filename), 'index.tsv')
            f = open(index_filename, 'ab')
            entry = '%s\t%s' % (os.path.basename(filename), url)
            f.write(entry.encode('utf-8'))
            f.close()
            # TODO log hash and original url to an index of some kind (sqlite3 db probably best)
    else:
        log.debug('getting cached file %r', filename)
        f = open(filename, 'rb')
        page = f.read()
        f.close()
    log.debug('page %d bytes', len(page))  # TODO human bytes
    return page


FORMAT_MARKDOWN = 'markdown'
FORMAT_HTML = 'html'  # (potentiall) raw html/xhtml only - no external images, fonts, css, etc.

def extract_from_page(url, page_content=None, output_format=None):
    """if content is provided, try and use that instead of pulling from URL - NOTE not guaranteed
    """
    output_format = output_format or FORMAT_HTML

    assert output_format in (FORMAT_HTML, FORMAT_MARKDOWN)  # TODO replace with actual check
    assert url.startswith('http')  # FIXME DEBUG

    if page_content is None:
        # TODO handle "file://" URLs? see FIXME above
        if url.startswith('http'):
            page_content_bytes = get_url(url)
        else:
            # assume read file local filename
            f = open(url, 'rb')
            page_content_bytes = f.read()
            f.close()

        page_content = page_content_bytes.decode('utf-8')  # FIXME revisit this - cache encoding

    doc_metadata = None
    # * python-readability does a great job at
    #   extracting main content as html
    # * trafilatura does a great job at extracting meta data, but content
    #   is not usable (either not html or text that looks like Markdown
    # with odd paragraph spacing (or lack of))
    #
    # Use both for now
    if trafilatura:
        doc_metadata = trafilatura.bare_extraction(page_content, include_links=True, include_formatting=True, include_images=True, include_tables=True, with_metadata=True, url=url)
        # TODO cleanup and return null for unknown entries

    doc = Document(page_content)  # python-readability

    content = doc.summary()  # Unicode string
    # NOTE at this point any head that was in original is now missing, including title information
    if not doc_metadata:
        """We have:
            .title() -- full title
            .short_title() -- cleaned up title
            .content() -- full content
            .summary() -- cleaned up content
        """
        doc_metadata = {
            'title': doc.short_title(),  # match trafilatura
            'description': doc.title(),
            'author': None,
            'date': None,  # TODO use now? Ideally if had http headers could use last-updated
        }

    if output_format == FORMAT_MARKDOWN:
        content = markdownify(content.encode('utf-8'))

    postlight_metadata = {
        "title": doc_metadata['title'],
        "author": doc_metadata['author'],
        "date_published": doc_metadata['date'],
        "dek": None,
        "lead_image_url": None,  # FIXME
        "content": content,
        "next_page_url": None,
        "url": url,
        "domain": None,  # FIXME
        "excerpt": None,  # FIXME
        "word_count": 0,  # FIXME
        "direction": "ltr",  # hard coded
        "total_pages": 1,  # hard coded
        "rendered_pages": 1  # hard coded
    }
    return postlight_metadata


def main(argv=None):
    if argv is None:
        argv = sys.argv

    print('Python %s on %s' % (sys.version, sys.platform))

    urls = argv[1:]  # no argument processing (yet)
    print(urls)
    output_format = os.environ.get('OUTPUT_FORMAT', FORMAT_HTML)
    for url in urls:
        x = extract_from_page(url, output_format=output_format)
        print(url)
        print(json.dumps(x, indent=4))

    return 0


if __name__ == "__main__":
    sys.exit(main())

