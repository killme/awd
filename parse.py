import json
import sys
import re
from bs4 import BeautifulSoup

def normalize_url(url: str) -> str:
    return url.replace(".html", "")

def before_hash(url: str) -> str:
    return url.split("#")[0]

def make_link(link):
    parent = link.parent
    href = normalize_url(link.attrs.get("href", ""))
    body = link.text.strip()
    classes = parent.attrs.get("class", [])

    if not body or not href or (
        href.startswith("#") or
        href.startswith("http://") or
        href.startswith("https://") or
        href.startswith("Thread") or
        "?oldid=" in href or
        "?openEditor=" in href or
        "reference-text" in classes or
        "wds-global-footer__links-list-item" in classes or
        "page-header__categories-links" in classes
    ):
        return None

    return {
        "target": {
            "page": before_hash(href),
            "href": href,
        },
        "body": body,
    }

def extract_link(links, link, l):
    key = "${link_%d}" % len(links)
    link.replace_with(key)

    l["key"] = key
    links += [ l ]

def make_body(text, inline):
    for v in inline:
        text = text.replace(v["key"], v["body"])

    return text.strip()

def generate_for(seed):
    page = seed.replace("avatar.wikia.com/wiki/", "").replace(".html", "")

    try:
        with open(seed, "r") as f:
            html = f.read()
    except:
        return None

    parsed_html = BeautifulSoup(html, "lxml")
    if not parsed_html.title:
        return None

    page_title = parsed_html.title.text.replace(" | Avatar Wiki | FANDOM powered by Wikia", "")

    for tag in [ 'i', 'b', 'em', 'small' ]:
        for remove in parsed_html.find_all(tag):
            remove.unwrap()
    for tag in parsed_html.select(".reference"):
        tag.decompose()

    article = parsed_html.find(id='WikiaArticle')
    if not article:
        return None

    canonical = parsed_html.find(attrs={"property": "og:url"}).attrs["content"]

    paragraphs = []
    for paragraph in article.find_all("p"):
        links = []

        for link in paragraph.find_all('a'):
            l = make_link(link)
            if l:
                extract_link(links, link, l)

        paragraphs += [{
            "body": paragraph.text.strip(),
            "text": make_body(paragraph.text, links),
            "links": links,
        }]

    categories = []
    for category in parsed_html.select("#articleCategories .categories a"):
        l = make_link(category)
        if l:
            categories += [ l ]

    def parse_value_item(item) -> str:
        links = []
        for link in item.find_all("a"):
            l = make_link(link)
            if l:
                extract_link(links, link, l)

        value = re.sub(r"\(.*?\)", "", item.text)

        extra = re.search(r"\((.*?)\)", item.text)
        extra = extra.group(0).strip() if extra else ""

        return {
            "value": value.strip(),
            "value_text": make_body(value, links),

            "extra": extra,
            "extra_text": make_body(extra, links),

            "body": item.text.strip(),
            "text": make_body(item.text, links),

            "links": links,
        }

    facts = []

    for aside in parsed_html.select("aside.portable-infobox"):
        for data_item in aside.select(".pi-item.pi-data"):
            # TODO: Grouping?
            key = data_item.select(".pi-data-label")
            value = data_item.select(".pi-data-value")

            if not key or not value:
                continue

            key = key[0]
            value = value[0]

            value_out = []

            if len(value.contents) == 1 and value.contents[0].name == "ul":
                for value_item in value.contents[0].contents:
                    value_out += [ parse_value_item(value_item) ]
            else:
                value_out = [ parse_value_item(value) ]

            facts += [
                {
                    "key": key.text.strip(),
                    "value": value_out,
                }
            ]


    return {
        "source": {
            "page": page,
            "canonical": canonical,
            "file": seed,
            "title": page_title,
        },
        "paragraphs": paragraphs,
        "categories": categories,
        "facts": facts,
    }

for seed in sys.argv[1:]:
    v = generate_for(seed)
    if v:
        dumped = json.dumps(v, sort_keys=True, indent=2)

        to = "data/" + v["source"]["page"] + ".json"
        print ("Writing", to)
        with open(to, "w") as f:
            f.write(dumped)
