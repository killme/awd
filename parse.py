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
    page = before_hash(href)
    body = link.text.strip()
    classes = parent.attrs.get("class", [])

    external = href.startswith("http://") or href.startswith("https://")
    if external and "avatar.wikia.com" in href:
        external = False
        href = re.sub(r"https?://avatar.wikia.com/wiki/", "", href)
        page = re.sub(r"https?://avatar.wikia.com/wiki/", "", page)
    if not external:
        href = "/wiki/" + href

    if not body or not href or (
        href.startswith("#") or
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
            "page": page,
            "href": href,
            "external": external,
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

def process_paragraph(paragraph, section):
    links = []

    for link in paragraph.find_all('a'):
        l = make_link(link)
        if l:
            extract_link(links, link, l)

    return {
        "section": list(section),
        "body": paragraph.text.strip(),
        "text": make_body(paragraph.text, links),
        "links": links,
    }

HEADER_LEVELS = {
    "h%d" % i: i
    for i in range (1, 10)
}

def generate_for(seed):
    page = seed.replace("avatar.wikia.com/wiki/", "").replace(".html", "")
    if page.startswith("Avatar_Wiki_") \
        or page.startswith("Blog_") \
        or page.startswith("Forum_") \
        or page.startswith("Special_") \
        or page.startswith("Template_") \
        or page.startswith("MediaWiki_") \
        or page.startswith("Board_") \
        or page.startswith("Topic_"):
        # Ignore "meta" pages
        return None

    try:
        with open(seed, "r") as f:
            html = f.read()
    except:
        return None

    parsed_html = BeautifulSoup(html, "lxml")
    if not parsed_html.title:
        return None

    page_title = parsed_html.title.text.replace(" | Avatar Wiki | FANDOM powered by Wikia", "")

    for tag in [ 'i', 'b', 'em', 'small', 'center' ]:
        for remove in parsed_html.find_all(tag):
            remove.unwrap()
    for tag in parsed_html.select(".reference"):
        # Remove inline [1] ref tags
        tag.decompose()
    for tag in parsed_html.select("#RelatedForumDiscussion"):
        # Remove discussion section from article
        tag.decompose()
    for tag in parsed_html.select(".category-page__alphabet-shortcuts, .category-page__total-number"):
        # Remove alphabeth indexing from category pages
        tag.decompose()

    article = parsed_html.find(id='WikiaArticle')
    if not article:
        return None
    article_body = article.find(id="mw-content-text")

    canonical = parsed_html.find(attrs={"property": "og:url"}).attrs["content"]

    section = [ page_title ]

    paragraphs = []
    for paragraph in article_body.contents:
        if not paragraph.name \
            or paragraph.name == "div" \
            or paragraph.name == "table" \
            or paragraph.name == "noscript" \
            or paragraph.name == "nav" \
            or paragraph.name == "aside" \
            or paragraph.name == "figure" \
            or paragraph.name == "dl" \
            or paragraph.name == "script" \
            or paragraph.name == "br" \
            or paragraph.name == "hr":
            continue

        heading = HEADER_LEVELS.get(paragraph.name)
        if heading:
            while len(section) >= heading:
                del section[len(section) - 1]

            section.append(paragraph.text.strip())
            continue

        if paragraph.name == "ul" or paragraph.name == "ol":
            for li in paragraph.find_all("li"):
                paragraphs += [process_paragraph(li, section)]
        elif paragraph.name == "p" or paragraph.name == "blockquote":
            paragraphs += [process_paragraph(paragraph, section)]
        elif paragraph.name == "a" or paragraph.name == "span":
            # Some text is not wrapped in a paragraph tag for some reason
            # (Example: http://avatar.wikia.com/wiki/Mitchell_Whitfield)
            # TODO: Auto wrap in a paragrap
            continue
        else:
            raise Exception("Unknown tag type: %s" % paragraph)

    for listing in article_body.select(".category-page__members"):
        while len(section) >= 2:
            del section[len(section) - 1]

        section.append("")

        for child in listing.contents:
            if child.name == "div":
                section[1] = child.text.strip()
            elif child.name == "ul":
                for li in child.find_all("li"):
                    paragraphs += [process_paragraph(li, section)]
            elif not child.name or child.name == "noscript":
                continue
            else:
                raise Exception("Unknown tag type: %s" % child)


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
    try:
        v = generate_for(seed)
        if v:
            dumped = json.dumps(v, sort_keys=True, indent=2)

            to = "data/" + v["source"]["page"] + ".json"
            # print ("Writing", to)
            with open(to, "w") as f:
                f.write(dumped)
    except Exception as e:
        print ("Failed to generate for", seed)
        raise
