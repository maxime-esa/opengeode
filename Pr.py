#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    OpenGEODE - A tiny SDL Editor for TASTE

    This module generates textual SDL code (PR format)
    by parsing the graphical symbols.

    Copyright (c) 2012-2014 European Space Agency

    Designed and implemented by Maxime Perrotin

    Contact: maxime.perrotin@esa.int
"""


import logging
from collections import deque
from itertools import chain
from singledispatch import singledispatch

import genericSymbols, sdlSymbols, Connectors

LOG = logging.getLogger(__name__)

__all__ = ['parse_scene', 'generate']


class Indent(deque):
    ''' Extension of the deque class to support automatic indenting '''
    indent = 0

    def append(self, string):
        ''' Redefinition of the append to insert the indent pattern '''
        super(Indent, self).append('    ' * Indent.indent + string)


def parse_scene(scene, full_model=False):
    ''' Return the PR string for a complete scene
        Optionally, also generate the SYSTEM structure, with channels, etc. '''
    #pr_data = deque()
    pr_data = Indent()
    if full_model:
        # Generate a complete SDL system - to have everything in a single file
        # (1) get system name
        # (2) get signal directions from the connection of the process to env
        # (3) generate all the text
        processes = list(scene.processes)
        system_name = unicode(processes[0]) if processes else u'OpenGEODE'
        pr_data.append('SYSTEM {};'.format(system_name))
        Indent.indent += 1
        channels, routes = Indent(), Indent()
        for each in scene.texts:
            # Parse text areas to retrieve signal names USELESS
           pr = generate(each)
           pr_data.extend(pr)
        if processes:
            to_env = processes[0].connection.out_sig
            from_env = processes[0].connection.in_sig
            if to_env or from_env:
                channels.append('CHANNEL c')
                Indent.indent += 1

                routes.append('SIGNALROUTE r')
                if from_env:
                    from_txt = 'FROM ENV TO {} WITH {};'\
                               .format(system_name, from_env)
                    channels.append(from_txt)
                    Indent.indent += 1
                    routes.append(from_txt)
                    Indent.indent -= 1
                if to_env:
                    to_txt = 'FROM {} TO ENV WITH {};'\
                              .format(system_name, to_env)
                    channels.append(to_txt)
                    Indent.indent += 1
                    routes.append(to_txt)
                    Indent.indent -= 1
            Indent.indent -= 1
            channels.append('ENDCHANNEL;')
            Indent.indent += 1
            routes.append('CONNECT c AND r;')
            Indent.indent -= 1

        pr_data.extend(channels)
        pr_data.append('BLOCK {};'.format(system_name))
        Indent.indent += 1
        pr_data.extend(routes)
        for each in processes:
            pr_data.extend(generate(each))
        Indent.indent -= 1
        pr_data.append('ENDBLOCK;')
        Indent.indent -= 1
        pr_data.append('ENDSYSTEM;')
        #print '\n'.join(pr_data)

    else:
        for each in scene.processes:
            pr_data.extend(generate(each))

        for each in chain(scene.texts, scene.procs, scene.start):
            pr_data.extend(generate(each))
        for each in scene.floating_labels:
            pr_data.extend(generate(each))
        composite = set(scene.composite_states.keys())
        for each in scene.states:
            if each.is_composite():
                # Ignore via clause:
                statename = unicode(each).split()[0].lower()
                try:
                    composite.remove(statename)
                    sub_state = generate(each, composite=True, nextstate=False)
                    if sub_state:
                        sub_state.reverse()
                        pr_data.extendleft(sub_state)
                except KeyError:
                    pass
            pr_data.extend(generate(each, nextstate=False))
    return list(pr_data)


def cif_coord(name, symbol):
    ''' PR string for the CIF coordinates/size of a symbol '''
    return u'/* CIF {symb} ({x}, {y}), ({w}, {h}) */'.format(
            symb=name,
            x=int(symbol.scenePos().x()), y=int(symbol.scenePos().y()),
            w=int(symbol.boundingRect().width()),
            h=int(symbol.boundingRect().height()))


def hyperlink(symbol):
    ''' PR string for the optional hyperlink associated to a symbol '''
    return u"/* CIF Keep Specific Geode HyperLink '{}' */".format(
                                                         symbol.text.hyperlink)


def common(name, symbol):
    ''' PR string format that is shared by most symbols '''
    result = Indent()
    result.append(cif_coord(name, symbol))
    if symbol.text.hyperlink:
        result.append(hyperlink(symbol))
    result.append(u'{} {}{}'.format(name, unicode(symbol.text), ';'
                                if not symbol.comment else ''))
    if symbol.comment:
        result.extend(generate(symbol.comment))
    return result


def recursive_aligned(symbol):
    ''' Get the branch following symbol '''
    result = Indent()
    Indent.indent += 1
    next_symbol = symbol.next_aligned_symbol()
    while next_symbol:
        result.extend(generate(next_symbol))
        next_symbol = next_symbol.next_aligned_symbol()
    Indent.indent -= 1
    return result


@singledispatch
def generate(symbol, *args, **kwargs):
    ''' Generate text for a symbol, recursively or not - return a list of
        strings '''
    _ = symbol
    raise NotImplementedError('Unsupported AST construct: {}'
                              .format(type(symbol)))
    return Indent()


@generate.register(genericSymbols.Comment)
def _comment(symbol, **kwargs):
    ''' Optional comment linked to a symbol '''
    result = Indent()
    result.append(cif_coord('COMMENT', symbol))
    if symbol.text.hyperlink:
        result.append(hyperlink(symbol))
    result.append(u'COMMENT \'{}\';'.format(unicode(symbol.text)))
    return result


@generate.register(sdlSymbols.Input)
def _input(symbol, recursive=True, **kwargs):
    ''' Input symbol or branch if recursive is set '''
    result = common('INPUT', symbol)
    if recursive:
        result.extend(recursive_aligned(symbol))
    return result


@generate.register(sdlSymbols.Connect)
def _connect(symbol, recursive=True, **kwargs):
    ''' Connect symbol or branch if recursive is set '''
    result = common('CONNECT', symbol)
    if recursive:
        result.extend(recursive_aligned(symbol))
    return result


@generate.register(sdlSymbols.Output)
def _output(symbol, **kwargs):
    ''' Output symbol '''
    return common('OUTPUT', symbol)


@generate.register(sdlSymbols.Decision)
def _decision(symbol, recursive=True, **kwargs):
    ''' Decision symbol or branch if recursive is set '''
    result = common('DECISION', symbol)
    if recursive:
        else_branch = None
        Indent.indent += 1
        for answer in symbol.branches():
            if unicode(answer).lower().strip() == 'else':
                else_branch = generate(answer)
            else:
                result.extend(generate(answer))
        if else_branch:
            result.extend(else_branch)
        Indent.indent -= 1
    result.append(u'ENDDECISION;')
    return result


@generate.register(sdlSymbols.DecisionAnswer)
def _decisionanswer(symbol, recursive=True, **kwargs):
    ''' Decision Answer symbol or branch if recursive is set '''
    result = Indent()
    Indent.indent += 1
    result.append(cif_coord('ANSWER', symbol))
    ans = unicode(symbol)
    if ans.lower().strip() != u'else':
        ans = u'({})'.format(ans)
    if symbol.text.hyperlink:
        result.append(hyperlink(symbol))
    result.append(u'{}:'.format(ans))
    if recursive:
        result.extend(recursive_aligned(symbol))
    Indent.indent -= 1
    return result


@generate.register(sdlSymbols.Join)
def _join(symbol, **kwargs):
    ''' Join symbol '''
    return common('JOIN', symbol)


@generate.register(sdlSymbols.ProcedureStop)
def _procedurestop(symbol, **kwargs):
    ''' Procedure Stop symbol '''
    return common('RETURN', symbol)


@generate.register(sdlSymbols.Task)
def _task(symbol, **kwargs):
    ''' Task symbol '''
    return common('TASK', symbol)


@generate.register(sdlSymbols.ProcedureCall)
def _procedurecall(symbol, **kwargs):
    ''' Procedure call symbol '''
    result = Indent()
    result.append(cif_coord('PROCEDURECALL', symbol))
    if symbol.text.hyperlink:
        result.append(hyperlink(symbol))
    result.append(u'CALL {}{}'.format(unicode(symbol.text), ';'
                                      if not symbol.comment else ''))
    if symbol.comment:
        result.extend(generate(symbol.comment))
    return result


@generate.register(sdlSymbols.TextSymbol)
def _textsymbol(symbol, **kwargs):
    ''' Text Area symbol '''
    result = Indent()
    result.append(cif_coord('TEXT', symbol))
    if symbol.text.hyperlink:
        result.append(hyperlink(symbol))
    result.append(unicode(symbol.text))
    result.append(u'/* CIF ENDTEXT */')
    return result


@generate.register(sdlSymbols.Label)
def _label(symbol, recursive=True, **kwargs):
    ''' Label symbol or branch if recursive is set '''
    result = Indent()
    result.append(cif_coord('LABEL', symbol))
    if symbol.text.hyperlink:
        result.append(hyperlink(symbol))
    if symbol.common_name == 'floating_label':
        result.append(u'CONNECTION {}:'.format(unicode(symbol)))
        if recursive:
            result.extend(recursive_aligned(symbol))
        result.append(u'/* CIF End Label */')
        result.append(u'ENDCONNECTION;')
    else:
        result.append(u'{}:'.format(unicode(symbol)))
    return result


@generate.register(sdlSymbols.State)
def _state(symbol, recursive=True, nextstate=True, composite=False, cpy=False,
           **kwargs):
    ''' State/Nextstate symbol or branch if recursive is set '''
    if nextstate and symbol.hasParent:
        result = common('NEXTSTATE', symbol)
    elif not composite and symbol.hasParent and not cpy \
            and not [each for each in symbol.childSymbols()
            if not isinstance(each, genericSymbols.Comment)]:
        # If nextstate has no child, don't generate anything
        result = []
    elif not composite:
        result = common('STATE', symbol)
        if recursive:
            Indent.indent += 1
            # Generate code for INPUT and CONNECT symbols
            for each in (symb for symb in symbol.childSymbols()
                         if isinstance(symb, sdlSymbols.Input)):
                result.extend(generate(each))
            Indent.indent -= 1
        result.append(u'ENDSTATE;')
    else:
        # Generate code for a nested state
        result = Indent()
        result.append('STATE {};'.format(unicode(symbol).split()[0]))
        result.append('SUBSTRUCTURE')
        Indent.indent += 1
        entry_points, exit_points = [], []
        for each in symbol.nested_scene.start:
            if unicode(each):
                entry_points.append(unicode(each))
        for each in symbol.nested_scene.returns:
            if unicode(each) != u'no_name':
                exit_points.append(unicode(each))
        if entry_points:
            result.append(u'in ({});'.format(','.join(entry_points)))
        if exit_points:
            result.append(u'out ({});'.format(','.join(exit_points)))
        Indent.indent += 1
        result.extend(parse_scene(symbol.nested_scene))
        Indent.indent -= 1
        Indent.indent -= 1
        result.append(u'ENDSUBSTRUCTURE;')
    return result


@generate.register(sdlSymbols.Process)
def _process(symbol, recursive=True, **kwargs):
    ''' Process symbol and inner content if recursive is set '''
    result = common('PROCESS', symbol)
    if recursive and symbol.nested_scene:
        Indent.indent += 1
        result.extend(parse_scene(symbol.nested_scene))
        Indent.indent -= 1
    result.append(u'ENDPROCESS {};'.format(unicode(symbol)))
    return result


@generate.register(sdlSymbols.Procedure)
def _procedure(symbol, recursive=True, **kwargs):
    ''' Procedure symbol or branch if recursive is set '''
    result = common('PROCEDURE', symbol)
    if recursive and symbol.nested_scene:
        Indent.indent += 1
        result.extend(parse_scene(symbol.nested_scene))
        Indent.indent -= 1
    result.append(u'ENDPROCEDURE;'.format(unicode(symbol)))
    return result


@generate.register(sdlSymbols.Start)
def _start(symbol, recursive=True, **kwargs):
    ''' START symbol or branch if recursive is set '''
    result = Indent()
    result.append(cif_coord('START', symbol))
    result.append(u'START{via}{comment}'
                  .format(via=(' ' + unicode(symbol) + ' ')
                          if unicode(symbol).replace('START', '') else '',
                          comment=';' if not symbol.comment else ''))
    if symbol.comment:
        result.extend(generate(symbol.comment))
    if recursive:
        result.extend(recursive_aligned(symbol))
    return result


@generate.register(Connectors.Signalroute)
def _channel(symbol, recursive=True, **kwargs):
    ''' Signalroute at block level '''
    result = Indent()
    result.append('SIGNALROUTE c')
    if symbol.out_sig:
        result.append('FROM {} TO ENV WITH {};'.format(unicode(symbol.process),
                                                       symbol.out_sig))
    if symbol.in_sig:
        result.append('FROM ENV TO {} WITH {};'.format(unicode(symbol.process),
                                                       symbol.in_sig))
    return result


