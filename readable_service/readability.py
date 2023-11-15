import math
import re
import requests

from bs4 import BeautifulSoup
from loguru import logger
from urllib.parse import urljoin


# All of the regular expressions in use within readability
regexps = {
    'unlikelyCandidatesRe': re.compile(r'combx|modal|comment|disqus|foot|header|menu|meta|nav|rss|shoutbox|sidebar|sponsor|social|teaserlist|time|tweet|twitter', re.I),
    'okMaybeItsACandidateRe': re.compile(r'and|article|body|column|main|story|entry|^post', re.I),
    'positiveRe': re.compile(r'article|body|content|entry|hentry|page|pagination|post|section|chapter|description|main|blog|text', re.I),
    'negativeRe': re.compile(r'combx|comment|contact|foot|footer|footnote|link|media|meta|promo|related|scroll|shoutbox|sponsor|utility|tags|widget', re.I),
    'divToPElementsRe': re.compile(r'<(a|blockquote|dl|div|img|ol|p|pre|table|ul)', re.I),
    'replaceBrsRe': re.compile(r'(<br[^>]*>[ \n\r\t]*){2,}', re.I),
    'replaceFontsRe': re.compile(r'<(\/?)font[^>]*>', re.I),
    'trimRe': re.compile(r'^\s+|\s+$', re.I),
    'normalizeRe': re.compile(r'\s{2,}', re.I),
    'killBreaksRe': re.compile(r'(<br\s*\/?>(\s|&nbsp;?)*){1,}', re.I),
    'videoRe': re.compile(r'http:\/\/(www\.)?(youtube|vimeo|youku|tudou|56|yinyuetai)\.com', re.I),
    'attributeRe': re.compile(r'blog|post|article', re.I)
}

class Readable:
    def __init__(self, url):
        self.url = url
        self.response = self._get_response()
        self.html_content = self.response.text
        self.soup = self._get_soup()
        self.article_content = str(self._grab_article_content())
        self.soup = self._get_soup()  # Reset soup to the original content because while grabbing article content, we modify the soup
        self.title = self.soup.title.text

    def _grab_article_content(self):
        self._trash_bad_nodes()
        candidates = self._assign_content_score_to_paras()
        top_candidate = self._get_top_candidate(candidates)
        article_content = self._create_article_content(top_candidate)
        self._prepare_article_content(article_content)
        return article_content


    def _get_response(self):
        res = requests.get(self.url)
        if res.status_code != 200:
            raise Exception(f'Failed to get url: {self.url}')
        return res

    def _get_soup(self):
        return BeautifulSoup(self.response.text, 'lxml')


    def _remove_unlikely_candidate(self, node):
        # Returns true if the node is removed
        unlikely_match_string = ' '.join(node.get('class', '')) + '\n' + ' '.join(node.get('id', ''))
        if regexps['unlikelyCandidatesRe'].search(unlikely_match_string) is not None and regexps['okMaybeItsACandidateRe'].search(unlikely_match_string) is None and node.name != 'html' and node.name != 'body':
            logger.info('Removing unlikely candidate - ' + unlikely_match_string)
            node.decompose()
            return True

        return False



    def _convert_div_to_p(self, node):
        try:
            logger.info('Altering div to p')
            new_node = self.soup.new_tag('p')
            new_node.string = node.string
            node.replace_with(new_node)
        except ValueError as e:
            logger.error(e)



    def _convert_textnode_followed_by_br_to_para_node(self, node):
        logger.info('Altering textnode followed by br to para node')
        new_node = self.soup.new_tag('p')
        new_node.string = node.string
        node.nextSibling.decompose()
        node.replace_with(new_node)



    def _convert_span_with_text_to_para(self, node):
        logger.info('Replacing text node with a span tag with the same content.')
        new_node = self.soup.new_tag('span')
        new_node.string = node.string
        node.replace_with(new_node)


    def _trash_bad_nodes(self):
        nodes = self.soup.find_all()
        preserve_unlikley_candidates = False

        for i in range(len(nodes)):
            node = nodes[i]
            if node.string is None:
                logger.debug(f'Empty node: {node.name}. Skipping...')
                continue
            continue_flag = False

            if not preserve_unlikley_candidates:
                continue_flag = self._remove_unlikely_candidate(node)


            # Turn all divs that don't have children block level elements into p's
            if not continue_flag and node.name == 'div':
                # If the div doesn't have any children block level elements, turn it into a p
                if regexps['divToPElementsRe'].search(node.decode_contents()) is None:
                    self._convert_div_to_p(node)
                # convert nodes with text to para
                else:  # Divs with children block level elements
                    children = node.find_all()
                    for child_node in children:
                        if child_node.string is None: continue
                        if child_node.nextSibling and child_node.nextSibling.name == 'br':
                            self._convert_textnode_followed_by_br_to_para_node(child_node)
                        else:
                            self._convert_span_with_text_to_para(child_node)


    def _assign_content_score_to_paras(self):
        all_paragraphs = self.soup.find_all('p')
        candidates = []
        for i in range(len(all_paragraphs)):
            paragraph = all_paragraphs[i]
            parent_node = paragraph.parent
            grandparent_node = parent_node.parent
            inner_text = paragraph.text

            # Initialize readability data
            if parent_node.readability is None:
                parent_node.readability = {'content_score': 0}
                candidates.append(parent_node)

            if grandparent_node.readability is None:
                grandparent_node.readability = {'content_score': 0}
                candidates.append(grandparent_node)

            content_score = 0

            # Add a point for the paragraph itself as a base.
            content_score += 1

            # Add points for any commas within this paragraph
            content_score += inner_text.count(',')

            # For every 100 characters in this paragraph, add another point. Up to 3 points.
            content_score += min(math.floor(len(inner_text) / 100), 3)

            # Add the score to the parent. The grandparent gets half.
            parent_node.readability['content_score'] += content_score
            grandparent_node.readability['content_score'] += content_score / 2

        return candidates


    def _get_link_density(self, node):
        links = node.find_all('a')
        text_length = len(node.text)
        if text_length == 0: return 0
        link_length = 0
        for link in links:
            href = link.get('href')
            if href is None or href == '' or href.startswith('#'): continue
            link_length += len(link.text)

        return link_length / text_length


    def _get_top_candidate(self, candidates):
        # After we've calculated scores, loop through all of the possible candidate nodes we found
        # and find the one with the highest score.
        top_candidate = None
        for cand in candidates:
            # Scale the final candidates score based on link density. Good content should have a
            # relatively small link density (5% or less) and be mostly unaffected by this operation.
            cand.readability['content_score'] = cand.readability['content_score'] * (1 - self._get_link_density(cand))
            logger.debug(f"Candidate: {cand.name} ({cand.readability['content_score']})")

            if top_candidate is None or cand.readability['content_score'] > top_candidate.readability['content_score']:
                top_candidate = cand

        return top_candidate
        

    def _create_article_content(self, top_candidate):
        article_content = self.soup.new_tag('div')
        article_content['id'] = 'readability-content'
        sibling_score_threshold = max(10, top_candidate.readability['content_score'] * 0.2)
        sibling_nodes = top_candidate.parent.children

        for sibling in sibling_nodes:
            append = False
            append = sibling == top_candidate
            if not append and (hasattr(sibling, 'readability') and sibling.readability is not None) and sibling.readability['content_score'] >= sibling_score_threshold:
                append = True

            if sibling.name == 'p':
                link_density = self._get_link_density(sibling)
                node_content = sibling.text
                node_length = len(node_content)

                if node_length > 80 and link_density < 0.25:
                    append = True
                elif node_length < 80 and link_density == 0 and node_content.find(',') != -1:
                    append = True

            if append:
                logger.debug(f"Appending node: {sibling.name}")
                article_content.append(sibling)

        return article_content


    def _clean_styles(self, node):
        if node.get('class', '') != ['readability-styled']:
            node.attrs.pop('style', None)

        for child in node.find_all():
            if child.string is not None and child.get('class', '') != ['readability-styled']:
                child.attrs.pop('style', None)


    def _kill_breaks(self, node):
        node.string = re.sub(regexps['killBreaksRe'], '<br />', node.decode_contents())


    def _clean(self, node, tag):
        target_list = node.find_all(tag)
        is_embed = tag == 'object' or tag == 'embed'

        for target in target_list:
            # Allow youtube and vimeo videos through as people usually want to see those.
            if is_embed and target.decode.search(regexps['videosRe']) is not None:
                continue
            target.decompose()


    def _get_class_weight(self, e):
        weight = 0

        # Look for a special classname
        if e.get('class', '') != '':
            if re.search(regexps['negativeRe'], str(e.get('class', ''))) is not None:
                weight -= 25

            if re.search(regexps['positiveRe'], str(e.get('class', ''))) is not None:
                weight += 25

        # Look for a special ID
        if e.get('id', '') != '':
            if re.search(regexps['negativeRe'], str(e.get('id', ''))) is not None:
                weight -= 25

            if re.search(regexps['positiveRe'], str(e.get('id', ''))) is not None:
                weight += 25

        return weight


    def _clean_headers(self, e):
        for header_index in range(1, 7):
            headers = e.find_all(f'h{header_index}')
            for head in headers:
                if self._get_class_weight(head) < 0 or self._get_link_density(head) > 0.33:
                    head.decompose()


    def _get_inner_text(self, e, normalize_spaces=True):
        text_content = e.text.strip()

        if normalize_spaces:
            return re.sub(regexps['normalizeRe'], ' ', text_content)
        else:
            return text_content


    def _get_char_count(self, e, s):
        return len(self._get_inner_text(e).split(s))


    def _clean_conditionally(self, e, tag):
        tags_list = e.find_all(tag)
        cur_tags_length = len(tags_list)

        # Gather counts for other typical elements embedded within.
        # Traverse backwards so we can remove nodes at the same time without effecting the traversal.
        for i in range(cur_tags_length - 1, -1, -1):
            weight = self._get_class_weight(tags_list[i])

            logger.debug(f'Cleaning Conditionally {tags_list[i]} ({tags_list[i].get("class", "")}:{tags_list[i].get("id", "")})'
                            f'{" with score " + tags_list[i].readability.contentScore if "readability" in tags_list[i] else ""}')
            
            if weight < 0:
                tags_list[i].decompose()
            elif self._get_char_count(tags_list[i], ',') < 10:

                # If there are not very many commas, and the number of
                # non-paragraph elements is more than paragraphs or other ominous signs, remove the element.

                p = len(tags_list[i].find_all('p'))
                img = len(tags_list[i].find_all('img'))
                li = len(tags_list[i].find_all('li')) - 100
                input = len(tags_list[i].find_all('input'))

                embed_count = 0
                embeds = tags_list[i].find_all('embed')
                for embed in embeds:
                    if embed.get('src', '') and embed.get('src', '').search(regexps['videoRe']) == -1:
                        embed_count += 1

                link_density = self._get_link_density(tags_list[i])
                content_length = len(self._get_inner_text(tags_list[i]))
                to_remove = False

                if img > p and img > 1:
                    to_remove = True
                elif li > p and tag not in ['ul', 'ol']:
                    to_remove = True
                elif input > math.floor(p / 3):
                    to_remove = True
                elif content_length < 25 and (img == 0 or img > 2):
                    to_remove = True
                elif weight < 25 and link_density > 0.2:
                    to_remove = True
                elif weight >= 25 and link_density > 0.5:
                    to_remove = True
                elif (embed_count == 1 and content_length < 75) or embed_count > 1:
                    to_remove = True

                if to_remove:
                    tags_list[i].decompose()


    def _remove_extra_paragraphs(self, node):
        for para in node.find_all('p'):
            img_count = len(para.find_all('img'))
            embed_count = len(para.find_all('embed'))
            object_count = len(para.find_all('object'))

            if img_count == 0 and embed_count == 0 and object_count == 0 and self._get_inner_text(para) == '':
                para.decompose()


    def _clean_single_header(self, e):
        for header_index in range(1, 7):
            headers = e.find_all(f'h{header_index}')
            for header in headers:
                if header.nextSibling is None:
                    header.decompose()



    def _fix_links(self, node):

        def fix_link(link):
            return urljoin(self.url, link)

        for img in node.find_all('img'):
            src = img.get('src', None)
            if src: img['src'] = fix_link(src)

        for a in node.find_all('a'):
            href = a.get('href', None)
            if href: a['href'] = fix_link(href)



    def _prepare_article_content(self, article_content):
        self._clean_styles(article_content)
        # kill_breaks(article_content, soup)  # It's still buggy
        self._clean(article_content, 'form')
        self._clean(article_content, 'object')
        if len(article_content.find_all('h1')) == 1:
            self._clean(article_content, 'h1')  # because we are already displaying the title
        if len(article_content.find_all('h2')) == 1:
            self._clean(article_content, 'h2')  # maybe they are using h2 as header 
        self._clean(article_content, 'iframe')
        self._clean_conditionally(article_content, 'table')
        self._clean_conditionally(article_content, 'ul')
        self._clean_conditionally(article_content, 'div')
        self._remove_extra_paragraphs(article_content)
        self._clean_single_header(article_content)
        self._fix_links(article_content)
