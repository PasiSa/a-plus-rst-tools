# -*- coding: utf-8 -*-
import docutils
from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util.compat import Directive
from cgi import escape
from collections import Counter
import re
import os
from sphinx.directives.code import CodeBlock
from sphinx.errors import SphinxError
from operator import itemgetter

import aplus_nodes

annotated_section_counts = Counter()

class AnnotationError(SphinxError):
    category = 'Annotation error'


def clean_path(path): 
  return re.sub(r"[/\\ :]+", "", path).replace(".rst", "") 

def new_annotated_section_id(source_file_path):
  idprefix = clean_path(source_file_path).replace(clean_path(os.getcwd()), "") 
  global annotated_section_counts
  annotated_section_counts[idprefix] += 1 
  return "%s_%s" % (idprefix, str(annotated_section_counts[idprefix]))

def slicer(stringList):
  for i in range(0, len(stringList)):
    yield stringList[i:i+1]

class annotated_node(nodes.General, nodes.Element): pass

class AnnotatedSection(Directive):
    has_content = True
    required_arguments = 0
    optional_arguments = 0
    option_spec = { }

    def run(self):
        self.assert_has_content()

        env = self.state.document.settings.env
        env.annotated_name = new_annotated_section_id(self.state_machine.get_source_and_line(self.lineno)[0])
        env.annotated_annotation_count = 0
        env.annotated_now_within = True

        node = annotated_node()

        for slice in slicer(self.content):
            if '.. code-block' in slice[0]:
                slice[0] = slice[0].replace('.. code-block', '.. altered-code-block')

        highest_annotation = self.assert_sanity(self.block_text)
        if not highest_annotation:
            return [self.state.document.reporter.error('Invalid annotation markers embedded in ' + self.block_text)]

        self.state.nested_parse(self.content, 0, node)
        node['name'] = env.annotated_name
        if env.annotated_annotation_count != highest_annotation:
            return [self.state.document.reporter.error('Mismatching number of annotation captions (n=%s) and the embedded annotation markers (n=%s) in %s' % (env.annotated_annotation_count, highest_annotation, self.block_text))]
        
        env.annotated_now_within = False

        return [node]

    def assert_sanity(self, content):
        annotation_numbers_present = set(map(lambda matching: int(matching[0]), re.findall(u"\d«", content)))
        highest_present = max(annotation_numbers_present)
        all_until_highest = set(range(1, highest_present + 1))
        if annotation_numbers_present != all_until_highest:
          return None
        else:
          return highest_present
          

def visit_annotated_node(self, node):
    self.body.append('<div class="annotated ex-%s">\n' % (node['name']))
    env = self.builder.env
    env.redirect = self.body # store original output
    self.body = []           # create an empty one to receive the contents of the feedback line

def depart_annotated_node(self, node):
    env = self.builder.env
    parsed_html = self.body  # extract generated feedback line
    self.body = env.redirect # restore original output

    self.body.append(postprocess(u''.join(parsed_html), node['name']))

    self.body.append("</div>\n")

def postprocess(html, annotation_id):
    processed   = []
    openstack   = []
    selfclosing = []

    for part in re.split(u'(\d«» |\d«|»|\n)', html):
        if u'«» ' in part:
            if (len(part) != 4) or (not part[0].isdigit()) or (part[3] != u' '):
                raise AnnotationError(u"Encountered illegal self-closing annotation tag in %s." % (annotation_id))
            processed.append('<span class="ex-%s loc%s">' % (annotation_id, part[0]))
            openstack.append(part[0])
            selfclosing.append(part[0])
        elif u'«' in part:
            if (len(part) != 2) or (not part[0].isdigit()):
                raise AnnotationError(u"Encountered illegal annotation open tag in %s." % (annotation_id))
            processed.append('<span class="ex-%s loc%s">' % (annotation_id, part[0]))
            openstack.append(part[0])
        elif part == u'»':
            if len(openstack) == 0:
                raise AnnotationError(u"Unbalanced annotation markers in %s." % (annotation_id))
            openstack.pop()
            processed.append('</span>')
        elif part == '\n':
            for tag in selfclosing:
                if len(openstack) == 0:
                    raise AnnotationError(u"Unbalanced annotation markers in %s." % (annotation_id))
                openstack.pop()
                processed.append('</span>')
            selfclosing = []
            processed.append(part)
        else:
            if  (u'«' in part) or (u'»' in part):
                raise AnnotationError(u"Encountered illegal annotation tag in %s." % (annotation_id))

            processed.append(part)

    if len(openstack) != 0:
        raise AnnotationError(u"Unbalanced annotation markers in %s." % (annotation_id)) ##

    return u''.join(processed)

class annotation_node(nodes.General, nodes.Element): pass

class Annotation(Directive):
    has_content = True
    required_arguments = 0
    optional_arguments = 0
    option_spec = { }

    def run(self):
        self.assert_has_content()

        env = self.state.document.settings.env

        if not env.annotated_now_within:
          return [self.state.document.reporter.error('Not within an "annotated" directive:' + self.block_text.replace('\n', ' '))]

        node = annotation_node()
        self.state.nested_parse(self.content, 0, node)
        env.annotated_annotation_count += 1
        node['annotation-number'] = env.annotated_annotation_count
        node['name-of-annotated-section'] = env.annotated_name
        return [node]

def visit_annotation_node(self, node):
    self.body.append('<div class="container codecomment comment-%s-%s">' % (node['name-of-annotated-section'], node['annotation-number']))

def depart_annotation_node(self, node):
    self.body.append("</div>\n")


class altered_node(nodes.General, nodes.Element): pass

class AlteredCodeBlock(CodeBlock):
    def run(self):
        openstack   = []
        selfclosing = []
        annotations = []

        line_num = 0
        loc  = 0

        for line in slicer(self.content):
            processed   = []        
            
            for part in re.split(u'(\d«» |\d«|»)', line[0]): 
                if u'«» ' in part:
                    openstack.append((part[0], line_num, loc))
                    selfclosing.append(part[0])
                elif u'«' in part:
                    openstack.append((part[0], line_num, loc))
                elif u'»' in part:
                    start = openstack.pop()
                    annotations.append((start[0], start[1], start[2], line_num, loc))
                else:
                    processed.append(part)
                    loc += len(part)
            
            for tag in selfclosing:
                start = openstack.pop()
                annotations.append((start[0], start[1], start[2], line_num, loc))

            selfclosing = []
            line_num += 1
            loc = 0

            line[0] = u''.join(processed)

        # run the original code-block on the now cleaned content
        originals = CodeBlock.run(self)

        # place the results as children of a node holding annotation info
        node = altered_node()
        node['annotations'] = annotations

        for item in originals:
            node.append(item)

        return [node]

def visit_altered_node(self, node):
    env = self.builder.env
    env.inner_redirect = self.body # store original output
    self.body = []           # create an empty one to receive the contents of the feedback line

def depart_altered_node(self, node):
    env = self.builder.env
    parsed_html = self.body  # extract generated feedback line
    self.body = env.inner_redirect # restore original output

    self.body.append(annotate(u''.join(parsed_html), node.parent['name'], node['annotations']))

def create_open_tag(number, section_name):
    return u'<span class="ex-%s loc%s">' % (section_name, number)

def create_close_tag(number, section_name):
    return u'</span>'

def turn_to_close_tag(tag):
    return u'</%s>' % re.findall(u'<(\w+).*?>', tag)[0]        

def annotate(html, section_name, annotations):
    # sorting the annotations by their ending points correctly orders the starting points
    # for two annotations starting in the same location are correctly nested 
    annotations = sorted(annotations, key = lambda x:x[3:5], reverse=True)

    from collections import defaultdict
    startpoint_map = defaultdict(list)
    endpoint_map   = defaultdict(list)

    # collect split points
    for a in annotations:
        number= a[0]
        start = a[1:3]
        end   = a[3:5]
        startpoint_map[start].append(number)
        endpoint_map[end].append(number)

    html = html.replace("<span></span>", "") # temporary workaround for extra span created by Sphinx in Python 3
    parts = re.split(u'(<pre.*?>|</pre>)', html)

    # separate tags from text
    original = re.split(u'(<.*?>|\n)', parts[2])
    
    #add splits
    line = 0
    loc  = 0
    result = []
    last_open  = u''

    for item in original:
        if u'</' in item:
            # closing tag

            result.append(item)
            last_open = u''

            # add any closing tags
            for number in endpoint_map[(line, loc)]:
                result.append(create_close_tag(number, section_name))

        elif u'<' in item:
            # opening tag

            # add tags for opening annotations
            for number in startpoint_map[(line, loc)]:
                result.append(create_open_tag(number, section_name))

            last_open = item
            result.append(item)
        elif u'\n' in item:
            # line change

            line += 1
            loc   = 0

            result.append(item)
        elif item:

            chars = re.findall('(&#?\w+;?|.)', item)

            # text element
            start_loc = loc
            end_loc   = loc + len(chars)

            # add tags for opening annotations
            if (not last_open):
                for number in startpoint_map[(line, loc)]:
                    result.append(create_open_tag(number, section_name))

            # iterate over possible split locations and append chars
            
            for char in chars:
                if (loc != start_loc) & (loc != end_loc) & (((line, loc) in endpoint_map) | ((line, loc) in startpoint_map)):
                    # somewhere in the middle
                    if last_open:
                        result.append(turn_to_close_tag(last_open))
                    for number in endpoint_map[(line, loc)]:
                       result.append(create_close_tag(number, section_name))
                    for number in startpoint_map[(line, loc)]:
                       result.append(create_open_tag(number, section_name))
                    if last_open:
                        result.append(last_open)

                result.append(char)
                loc += 1

            # add tags for closing annotations
            if (not last_open):
                for number in endpoint_map[(line, loc)]:
                    result.append(create_close_tag(number, section_name))

    content = u''.join(result)
    return u''.join([parts[0], parts[1], content, parts[3], parts[4]])


def setup(app):

    ignore_visitors = (aplus_nodes.visit_ignore, aplus_nodes.depart_ignore)

    app.add_node(annotated_node, html=(visit_annotated_node, depart_annotated_node),
            latex=ignore_visitors)
    app.add_directive('annotated', AnnotatedSection)

    app.add_node(annotation_node, html=(visit_annotation_node, depart_annotation_node),
            latex=ignore_visitors)
    app.add_directive('annotation', Annotation)

    app.add_node(altered_node, html=(visit_altered_node, depart_altered_node),
            latex=ignore_visitors)
    app.add_directive('altered-code-block', AlteredCodeBlock)
