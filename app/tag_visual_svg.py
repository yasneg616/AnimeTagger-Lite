"""Compose original, non-photographic SVG diagrams from local primitives."""

from __future__ import annotations

from html import escape
from functools import lru_cache
import json
import math
from pathlib import Path
import re

from app.tag_visuals import TagVisual

BODY_LOCATIONS = {
    'head':(64,22), 'forehead':(64,13), 'face':(64,22), 'cheek':(55,25), 'chin':(64,31),
    'mouth':(64,27), 'hair':(64,12), 'ear':(78,23), 'neck':(64,34), 'shoulder':(47,43),
    'breast':(64,51), 'chest':(64,51), 'pectoral':(64,51), 'collarbone':(64,40), 'armpit':(47,52),
    'stomach':(64,64), 'navel':(64,68), 'midriff':(64,64), 'abs':(64,61), 'back':(64,60),
    'waist':(64,72), 'hip':(73,77), 'thigh':(76,90), 'leg':(77,98), 'knee':(77,98),
    'foot':(80,112), 'feet':(80,112), 'toe':(83,113), 'finger':(93,78), 'hand':(93,75),
    'arm':(86,62), 'groin':(64,77), 'ass':(64,80), 'skin':(64,57),
}


def _path(d: str, fill: str = "none", stroke: str = "{ink}", width: float = 3) -> str:
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'


def _circle(x: float, y: float, r: float, fill: str = "{fill}", stroke: str = "{ink}") -> str:
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>'


def _rect(x: float, y: float, w: float, h: float, fill: str = "{fill}", radius: float = 4) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{{ink}}" stroke-width="2.5"/>'


def _text(text: str, x: float = 64, y: float = 77, size: int = 27) -> str:
    return f'<text x="{x}" y="{y}" text-anchor="middle" font-family="Microsoft YaHei,Segoe UI,sans-serif" font-size="{size}" fill="{{ink}}">{escape(text)}</text>'


def _arrow(x1: float, y1: float, x2: float, y2: float, color: str = "{accent}") -> str:
    return _path(f'M{x1} {y1} L{x2} {y2}', stroke=color, width=4) + f'<path d="M-7 -5 L0 0 L-7 5" fill="none" stroke="{color}" stroke-width="3" transform="translate({x2} {y2}) rotate({math.degrees(math.atan2(y2-y1,x2-x1))})"/>'


def _star(cx: float, cy: float, r: float = 14, fill: str = "{fill}") -> str:
    points = []
    for i in range(10):
        a = math.pi * i / 5 - math.pi / 2
        radius = r if i % 2 == 0 else r * .44
        points.append(f'{cx+math.cos(a)*radius:.2f},{cy+math.sin(a)*radius:.2f}')
    return f'<polygon points="{" ".join(points)}" fill="{fill}" stroke="{{ink}}" stroke-width="2"/>'


def _person(x: float = 64, y: float = 21, scale: float = 1, pose: str = "standing") -> str:
    arms = 'M50 45 L39 65 L36 77 M78 45 L89 65 L92 77'
    legs = 'M64 73 L51 96 L48 112 M64 73 L77 96 L80 112'
    if any(v in pose for v in ('arms_up', 'hands_up', 'v_arms', '\\o/')):
        arms = 'M50 45 L36 28 L29 11 M78 45 L92 28 L99 11'
    elif any(v in pose for v in ('arm_up', 'hand_up')):
        arms = 'M50 45 L36 28 L29 11 M78 45 L89 65 L92 77'
    elif 'outstretched_arms' in pose or pose in {'t_pose', 'spread_arms'}:
        arms = 'M50 45 L28 46 L8 46 M78 45 L100 46 L120 46'
    elif 'outstretched_arm' in pose or 'pointing' in pose or 'reaching' in pose:
        arms = 'M50 45 L28 46 L8 46 M78 45 L89 65 L92 77'
    elif 'crossed_arms' in pose:
        arms = 'M50 45 L40 63 L77 58 M78 45 L88 67 L51 63'
    elif 'behind_head' in pose:
        arms = 'M50 45 L31 38 L49 25 M78 45 L97 38 L79 25'
    elif 'behind_back' in pose:
        arms = 'M50 45 L42 63 L64 70 M78 45 L86 63 L64 70'
    elif pose in {'arm_at_side', 'arms_at_sides'}:
        arms = 'M50 45 L47 67 L46 80 M78 45 L81 67 L82 80'
    elif 'on_own_hip' in pose or 'on_own_waist' in pose:
        arms = 'M50 45 L32 60 L55 73 M78 45 L96 60 L73 73' if 'hands_' in pose else 'M50 45 L39 65 L36 77 M78 45 L96 60 L73 73'
    elif any(v in pose for v in ('on_own_face', 'on_own_cheek', 'on_own_head', 'in_own_hair', 'on_own_mouth', 'to_mouth')):
        arms = 'M50 45 L34 38 L55 24 M78 45 L89 65 L92 77'
    elif 'on_own_chest' in pose:
        arms = 'M50 45 L38 62 L65 51 M78 45 L89 65 L92 77'
    elif pose.startswith(('hand_on_own_', 'hands_on_own_', 'hand_in_own_')):
        target = next((point for part,point in BODY_LOCATIONS.items() if pose.endswith('_'+part)), (64,60))
        arms = f'M50 45 L31 60 L{target[0]} {target[1]} M78 45 L89 65 L92 77'
    if 'sitting' in pose or pose in {'wariza', 'seiza', 'knees_up', 'hugging_own_legs'}:
        legs = 'M64 73 L94 75 L94 109 M64 73 L58 84 L58 111'
        if 'crossed' in pose:
            legs = 'M64 73 L90 83 L45 103 M64 73 L40 85 L83 104'
        if pose in {'wariza', 'seiza'}:
            legs = 'M64 73 L47 103 L30 94 M64 73 L81 103 L98 94'
        if pose in {'knees_up', 'hugging_own_legs'}:
            legs = 'M64 73 L85 56 L92 103 M64 73 L76 59 L80 105'
    elif pose == 'kneeling':
        legs = 'M58 73 L51 102 L77 111 M70 73 L72 102 L101 111'
    elif pose in {'on_one_knee', 'knee_up'}:
        legs = 'M64 73 L47 101 L27 103 M64 73 L86 72 L88 108'
    elif pose in {'squatting', 'all_fours', 'crawling'}:
        legs = 'M64 73 L39 81 L55 111 M64 73 L89 81 L73 111'
    elif pose in {'standing_on_one_leg', 'leg_up', 'leg_lift'}:
        legs = 'M64 73 L60 97 L60 113 M64 73 L83 68 L99 77'
    elif pose in {'walking', 'running', 'jumping', 'floating', 'flying'}:
        legs = 'M64 73 L43 91 L25 103 M64 73 L85 86 L105 75'
        arms = 'M50 45 L37 54 L22 45 M78 45 L88 36 L105 36'
    elif pose == 'crossed_legs':
        legs = 'M64 73 L76 96 L49 113 M64 73 L51 96 L79 113'
    elif pose in {'legs_apart', 'spread_legs'}:
        legs = 'M64 73 L40 96 L18 111 M64 73 L88 96 L110 111'
    elif pose == 'legs_together':
        legs = 'M61 73 L60 97 L58 112 M67 73 L68 97 L70 112'
    shape = _circle(64, 22, 12, '{paper}') + _path('M50 45 Q64 34 78 45 L72 73 L56 73 Z', '{fill}')
    shape += _path('M64 34 L64 41', width=5) + _path(arms, width=5) + _path(legs, width=5)
    if pose in {'on_back', 'lying', 'on_side', 'on_stomach', 'reclining'}:
        if pose == 'on_side':
            shape = _circle(64,22,12,'{paper}') + _path('M64 34 L64 75 L53 92 L73 110 M64 75 L76 89 L84 106 M64 44 L45 58 L47 32',width=6)
        elif pose == 'on_stomach':
            shape += _path('M52 23 l9 3 l-9 4',width=2)
        elif pose == 'on_back':
            shape += _path('M76 19 l-9 3 l9 4',width=2)
        shape = f'<g transform="translate(9 120) rotate(-90) scale(.85)">{shape}</g>'
    elif pose in {'leaning_forward', 'bent_over'}:
        shape = f'<g transform="translate(29 -10) rotate(24 64 74)">{shape}</g>'
    elif pose in {'leaning_back', 'arched_back', 'head_back'}:
        shape = f'<g transform="rotate(-20 64 74)">{shape}</g>'
    return f'<g transform="translate({x-64*scale} {y-21*scale}) scale({scale})">{shape}</g>'


def hair_diagram(variant: str, features: set[str]) -> str:
    short = any(v in variant for v in ('short', 'bob_cut', 'pixie', 'bowl', 'buzz', 'undercut'))
    bottom = 83 if short else 116
    if any(v in variant for v in ('ponytail', 'twintail', 'braid')) and not any(v in variant for v in ('half_up', 'partially_braided')):
        bottom = 84
    if 'medium' in variant:
        bottom = 98
    result = _path(f'M30 65 Q18 15 64 12 Q110 15 98 65 L105 {bottom} L22 {bottom} Z', '{fill}')
    result += _path('M37 52 Q34 91 64 95 Q94 91 91 52 Q66 32 37 52Z', '{paper}')
    result += _circle(51, 65, 3, '{ink}') + _circle(77, 65, 3, '{ink}') + _path('M58 82 Q64 85 70 82', width=2)
    if 'bald' in variant:
        bald = _circle(64, 58, 37, '{paper}') + _circle(51, 61, 3, '{ink}') + _circle(77, 61, 3, '{ink}')
        return bald + (_path('M25 44 L35 28 M103 44 L93 28 M64 20 L65 8',stroke='{fill}',width=4) if 'balding' in variant else '')
    bangs = 'M31 47 Q37 23 64 23 Q91 23 97 47 L88 58 L78 46 L68 57 L56 46 L43 57 Z'
    if 'blunt' in variant or 'hime' in variant or 'bowl' in variant:
        bangs = 'M31 47 Q37 23 64 23 Q91 23 97 47 L97 54 L31 54 Z'
    elif 'parted' in variant or 'swept' in variant:
        bangs = 'M31 55 Q30 17 64 23 Q100 18 97 55 Q74 49 64 30 Q54 48 31 55Z'
    elif 'over_one_eye' in variant or 'one_eye_covered' in variant:
        bangs = 'M30 49 Q35 18 67 23 Q91 24 97 49 L78 52 L62 83 L48 69 L32 82 Z'
    elif 'over_eyes' in variant:
        bangs = 'M30 49 Q35 18 64 23 Q94 24 98 49 L93 75 L80 68 L65 78 L49 69 L33 76 Z'
    elif 'between_eyes' in variant:
        bangs = 'M31 47 Q38 22 64 23 Q90 22 97 47 L78 50 L69 47 L64 79 L57 48 L43 57 Z'
    result += _path(bangs, '{fill}')
    if 'twintail' in variant or 'two_side_up' in variant or 'twin_braid' in variant or 'twin_drill' in variant:
        result += _path('M29 42 Q4 35 9 68 Q8 102 20 115 Q32 88 28 58Z', '{fill}')
        result += _path('M99 42 Q124 35 119 68 Q120 102 108 115 Q96 88 100 58Z', '{fill}')
    elif 'ponytail' in variant or 'one_side_up' in variant:
        tail_y = 66 if 'low' in variant else 25 if 'high' in variant else 38
        result += _path(f'M91 {tail_y} Q123 {tail_y-13} 117 {tail_y+28} Q110 94 108 118 Q94 104 96 {tail_y+31}Z', '{fill}')
        result += _circle(97, tail_y+4, 5, '{accent}')
    if 'bun' in variant or 'hair_rings' in variant:
        result += _circle(35, 24, 15, '{fill}' if 'rings' not in variant else '{paper}')
        if 'double' in variant or 'rings' in variant:
            result += _circle(93, 24, 15, '{fill}')
    if 'side-bun' in features:
        result += _circle(105,51,17,'{fill}')
    if 'bun-braid' in features:
        result += _circle(35,24,17,'{fill}') + _path('M25 15 L44 33 M24 30 L44 16',width=2)
    if 'folded' in features:
        result += _path('M108 110 Q121 64 98 57',stroke='{accent}',width=6)
    if 'braid' in variant and 'crown_braid' not in variant:
        positions = [20, 108] if 'twin' in variant else [100]
        for x in positions:
            result += _path(f'M{x-6} 52 Q{x-13} 61 {x-7} 66 Q{x-15} 74 {x-7} 81 Q{x-14} 89 {x-6} 96 L{x} 116 L{x+6} 96 Q{x+14} 89 {x+7} 81 Q{x+15} 74 {x+7} 66 Q{x+13} 61 {x+6} 52Z','{fill}',width=2)
            for y in (64, 78, 92, 106):
                result += _path(f'M{x-6} {y-4} l12 8 M{x+6} {y-4} l-12 8', width=2)
    if 'crown-braid' in features:
        result += _path('M30 48 Q64 5 98 48',stroke='{accent}',width=12)
        for x,y in ((36,36),(48,26),(64,22),(80,26),(92,36)):
            result += _path(f'M{x-4} {y-4} l8 8 M{x+4} {y-4} l-8 8',width=2)
    if 'french-braid' in features:
        result += _path('M64 27 L64 54',stroke='{accent}',width=8) + _path('M49 28 L67 37 L49 42 L67 50 L51 56',width=2)
    if 'tentacle' in features:
        result += _path('M29 74 Q-5 105 20 115 Q49 124 38 103 M99 74 Q133 105 108 115 Q79 124 90 103',stroke='{fill}',width=10)
    if 'ahoge' in variant or 'antenna' in variant:
        result += _path('M63 24 Q72 -5 91 7 Q67 5 63 24', '{fill}')
        if 'antenna' in variant:
            result += _path('M62 24 Q53 -5 34 7 Q58 5 62 24', '{fill}')
    if any(v in variant for v in ('wavy', 'curly', 'drill', 'fluffy', 'messy')):
        for x in (25, 96):
            result += _path(f'M{x} 48 q-9 11 2 20 q10 10 -1 20 q-9 10 1 20', stroke='{ink}', width=3)
        if 'curly' in variant or 'drill' in variant:
            for x in (23,105):
                for y in (57,76,95):
                    result += _path(f'M{x} {y} q-12 -10 -14 4 q-2 12 10 10 q13 -3 4 -11',width=2)
    if 'sidelock' in variant or 'hime' in variant or 'long_locks' in variant:
        result += _path('M34 47 L37 101 L47 98 L44 55 M94 47 L91 101 L81 98 L84 55', '{fill}')
    if 'hair_intakes' in variant:
        result += _path('M30 45 L47 23 L49 44 M98 45 L81 23 L79 44', '{fill}')
    if 'behind_ear' in variant:
        result += _circle(96,65,8,'{paper}') + _path('M97 58 q-8 4 -2 11 M91 45 L106 57',width=2)
    if 'blunt_ends' in variant:
        result += _path('M22 111 L105 111',stroke='{accent}',width=5)
    if 'asymmetrical' in variant:
        result += _path('M32 45 L46 103 L56 54','{fill}')
    if 'hair_spread_out' in variant:
        result += _path('M29 74 L5 92 L27 87 L8 118 L44 112 M99 74 L123 92 L101 87 L120 118 L84 112','{fill}')
    if 'hair_down' in variant or 'curtained' in variant:
        result += _path('M32 38 L36 114 M96 38 L92 114',width=2)
    if 'floating' in variant or 'flaps' in variant:
        result += _path('M30 49 Q0 62 5 29 M98 49 Q128 62 123 29', stroke='{fill}', width=7)
    if 'crossed_bangs' in variant:
        result += _path('M41 28 L79 60 M86 28 L51 60',stroke='{fill}',width=10)
    if 'half_updo' in variant or 'low-tied' in variant:
        result += _circle(99,73 if 'low-tied' in variant else 39,7,'{accent}')
    if 'low_twintails' in variant:
        result += _circle(23,78,6,'{accent}') + _circle(105,78,6,'{accent}')
    if 'two_side_up' in variant or 'one_side_up' in variant:
        result += _path('M42 92 L40 119 L88 119 L86 92','{fill}')
    if 'spiked' in variant:
        result += _path('M28 35 L25 14 L44 21 L52 3 L68 17 L81 3 L87 25 L111 17 L101 38', '{fill}')
    if 'gradient' not in variant and 'gradient' not in features and any(v in features or v in variant for v in ('two-tone', 'two_tone', 'streaked', 'colored_inner', 'multicolored')):
        result += _path('M31 29 Q49 14 64 17 L64 40 L47 51 L34 44Z', '{accent}', width=1)
        result += _path(f'M24 79 L35 78 L36 {bottom-4} L25 {bottom-4}Z', '{accent}', width=1)
    if 'multicolored' in variant or 'multicolored' in features:
        result += _path('M67 18 Q87 20 95 43 L82 47 L75 30Z', '#579bd4', width=1)
        result += _path(f'M94 78 L104 80 L104 {bottom-4} L93 {bottom-4}Z', '#6aa780', width=1)
    return result


def eyes_diagram(variant: str, features: set[str]) -> str:
    if 'jitome' in features:
        variant += '_jitome'
    result = ''
    for x, left in ((33, True), (95, False)):
        closed = 'closed_eyes' in variant or ('one_eye_closed' in variant and left)
        if closed:
            result += _path(f'M{x-25} 64 Q{x} 80 {x+25} 64', width=5)
            continue
        result += _path(f'M{x-26} 65 Q{x} 35 {x+26} 65 Q{x} 88 {x-26} 65Z', '{fill}' if 'sclera' in variant else '{paper}')
        color = '{accent}' if ('heterochromia' in variant or 'two-tone' in features) and not left else '{fill}'
        result += _circle(x, 63, 16, '#579bd4' if 'pupil' in variant and not any(t in variant for t in ('slit','heart','star','symbol','ringed','no_')) else '{paper}' if 'sclera' in variant else color)
        if 'multicolored' in variant or 'multicolored' in features:
            result += _path(f'M{x} 63 L{x} 47 A16 16 0 0 1 {x+16} 63Z', '{accent}', stroke='none', width=0)
            result += _path(f'M{x} 63 L{x+16} 63 A16 16 0 0 1 {x} 79Z', '#579bd4', stroke='none', width=0)
        if 'heart' in variant:
            result += _path(f'M{x} 68 c-17 -9 -10 -20 0 -11 c10 -9 17 2 0 11Z', '{ink}', width=1)
        elif 'star' in variant:
            result += _star(x, 63, 10, '{ink}')
        elif 'slit' in variant:
            result += _path(f'M{x} 48 L{x+3} 63 L{x} 78 L{x-3} 63Z', '{ink}', width=1)
        elif 'symbol-shaped' in variant:
            result += _star(x,63,10,'{ink}')
        elif 'ringed' in variant:
            result += _circle(x,63,10,'none')
        elif 'no_pupils' not in variant and 'empty_eyes' not in variant:
            result += _circle(x, 63, 7, '{fill}' if 'pupils' in variant else '#19202b', '#19202b')
        if 'bright' in variant or 'white_pupil' in variant:
            result += _circle(x-4, 59, 4, '#ffffff', 'none')
        if 'half-closed' in variant or 'half_closed' in variant:
            result += _path(f'M{x-25} 56 L{x+25} 56', width=6)
        if 'eyelash' in variant:
            result += _path(f'M{x-19} 53 l-6 -7 M{x} 46 l0 -8 M{x+19} 53 l6 -7', width=3)
        if 'small-pupils' in features:
            result += _circle(x,63,14,'{fill}') + _circle(x,63,3,'{ink}')
        if features & {'cross-pupils','x-pupils','diamond-pupils','horizontal-pupils'}:
            result += _circle(x,63,12,'{fill}')
            if 'diamond-pupils' in features:
                result += _path(f'M{x} 49 L{x+8} 63 L{x} 77 L{x-8} 63Z','{ink}')
            elif 'x-pupils' in features:
                result += _path(f'M{x-7} 56 L{x+7} 70 M{x-7} 70 L{x+7} 56',width=4)
            else:
                result += _path(f'M{x-11} 63 L{x+11} 63'+(f' M{x} 52 L{x} 74' if 'cross-pupils' in features else ''),width=4)
        if 'blank-eyes' in features:
            result += _circle(x,63,19,'{paper}')
        if 'narrow-eyes' in features:
            result += _path(f'M{x-26} 54 L{x+26} 54',stroke='{paper}',width=14) + _path(f'M{x-26} 61 L{x+26} 61',width=4)
        if 'wide-eyed' in variant:
            result += _circle(x,63,25,'none')
        if 'jitome' in variant:
            result += _path(f'M{x-26} 52 L{x+26} 52',width=6)
    if 'tsurime' in variant:
        result += _path('M7 51 L58 39 M70 39 L121 51', width=4)
    elif 'tareme' in variant:
        result += _path('M7 39 L58 51 M70 51 L121 39', width=4)
    if 'glowing' in variant:
        result += _star(64, 24, 13, '{accent}')
    if 'third_eye' in variant:
        result += _circle(64,22,13,'{fill}') + _circle(64,22,5,'{ink}')
    if 'eyes_visible_through_hair' in variant:
        result += '<g opacity=".35">' + _path('M15 16 L18 84 L48 26 L65 81 L100 24 L113 84','{fill}',width=7) + '</g>'
    if 'covered' in features:
        result += _rect(4,44,120,39,'{fill}') + _path('M48 48 L39 75',stroke='{accent}',width=2)
    return result


def face_diagram(variant: str, features: set[str]) -> str:
    result = _circle(64, 61, 43, '{paper}')
    smile = any(x in variant for x in ('smile', 'happy', 'grin', ':d', ';d', '^_^'))
    closed = any(x in variant for x in ('closed_eyes', 'sleeping', '^_^', '>_<'))
    if 'looking' in variant or 'eye_contact' in variant or 'glance' in variant:
        shift_x = -6 if 'side' in variant or 'away' in variant or 'back' in variant else 0
        shift_y = -5 if 'up' in variant else 5 if 'down' in variant else 0
        result += _circle(47, 53, 11, '#ffffff') + _circle(81, 53, 11, '#ffffff')
        result += _circle(47+shift_x, 53+shift_y, 4, '#19202b', '#19202b') + _circle(81+shift_x, 53+shift_y, 4, '#19202b', '#19202b')
        if shift_x or shift_y:
            result += _arrow(94, 34, 94+shift_x*3, 34+shift_y*3)
    elif closed:
        result += _path('M34 51 Q47 61 58 51 M70 51 Q82 61 94 51', width=4)
    else:
        result += _circle(47, 54, 5, '{ink}') + _circle(81, 54, 5, '{ink}')
        if 'one_eye_closed' in variant or ';d' in variant:
            result += _path('M34 54 L59 54', stroke='{paper}', width=13) + _path('M35 52 Q47 59 58 52', width=4)
    if smile:
        result += _path('M43 76 Q64 100 85 76 Z', '#ffffff')
    elif 'open_mouth' in variant or 'surprised' in variant or ':o' in variant:
        result += _circle(64, 82, 10, '{accent}')
    elif 'frown' in variant or 'angry' in variant or ':<' in variant:
        result += _path('M46 87 Q64 70 82 87', width=4)
    elif 'wavy_mouth' in variant or ':3' in variant:
        result += _path('M46 80 q9 12 18 0 q9 12 18 0', width=3)
    else:
        result += _path('M51 81 L77 81', width=3)
    if any(x in variant for x in ('blush', 'embarrass')):
        result += _path('M31 69 l4 -6 M39 72 l4 -6 M85 72 l4 -6 M93 69 l4 -6', stroke='#ec799a', width=3)
    if 'cry' in variant or 'tear' in variant:
        result += _path('M35 63 Q21 84 35 87 Q49 84 35 63Z', '#6fbcec', width=1)
        result += _path('M93 63 Q79 84 93 87 Q107 84 93 63Z', '#6fbcec', width=1)
    if 'angry' in variant or 'furrowed' in variant or 'v-shaped' in variant:
        result += _path('M35 35 L57 44 M71 44 L93 35', width=4)
    elif 'eyebrow' in variant:
        result += _path('M34 37 L59 37 M69 37 L94 37', width=6 if 'thick' in variant else 3)
    if 'tongue' in variant or ':p' in variant:
        result += _path('M55 81 L55 96 Q64 105 73 96 L73 81Z', '#f596aa')
    if 'fang' in variant or 'teeth' in variant:
        result += _path('M46 77 L52 88 L58 77 M71 77 L78 88 L84 77', '#ffffff', width=1)
    if 'sweat' in variant:
        result += _path('M107 25 Q96 42 107 48 Q118 42 107 25Z', '#6fbcec', width=1)
    if 'beard' in variant or 'facial_hair' in variant:
        result += _path('M29 70 Q64 104 99 70 L88 103 L64 118 L40 103 Z', '{fill}')
    elif 'mustache' in variant:
        result += _path('M64 73 Q42 56 34 77 Q48 91 64 78 Q80 91 94 77 Q86 56 64 73Z','{fill}')
    if 'dot_nose' in variant:
        result += _circle(64,67,3,'{ink}','none')
    if 'skin_fang' in variant:
        result += _path('M50 78 L57 88 L64 78','{paper}',width=1)
    if '^^^' in variant:
        result += _path('M44 81 l7 -9 l7 9 l7 -9 l7 9 l7 -9 l7 9',width=3)
    if 'eyeshadow' in variant:
        result += _path('M34 43 L59 43 M69 43 L94 43',stroke='{accent}',width=7)
    if '@_@' in variant:
        result += _path('M37 53 q0 -14 15 -10 q14 4 8 16 q-8 15 -22 5 M72 53 q0 -14 15 -10 q14 4 8 16 q-8 15 -22 5',width=3)
    if 'makeup' in variant or 'lipstick' in variant or 'lips' == variant:
        result += _path('M46 82 Q59 70 64 78 Q69 70 82 82 Q64 94 46 82Z', '#dc6f8e', width=1)
    if 'pout' in features:
        result += _path('M47 84 Q64 100 81 84 M56 92 L72 92',stroke='{accent}',width=4)
    if 'smirk' in features:
        result += _path('M51 81 L77 81',stroke='{paper}',width=7) + _path('M47 86 Q70 89 84 73',width=3)
    if 'serious' in features:
        result += _path('M35 39 L57 39 M71 39 L93 39',width=4)
    if 'raised_eyebrows' in variant:
        result += _path('M33 27 Q48 18 59 28 M69 28 Q82 18 95 27',width=4)
    if 'short_eyebrows' in variant:
        result += _path('M41 36 L51 36 M77 36 L87 36',stroke='{accent}',width=4)
    if 'under-eyes' in features:
        result += _path('M35 65 Q46 71 58 65 M70 65 Q82 71 94 65',stroke='{accent}',width=3)
    if 'eyeliner' in features:
        result += _path('M32 52 Q47 43 59 52 M69 52 Q82 43 96 52',width=4)
    if 'nose' in features:
        result += _path('M64 59 L58 72 L69 72',width=2)
    if 'no-nose' in features:
        result += _circle(64,67,10,'none') + _path('M56 75 L72 59',stroke='{accent}',width=3)
    if 'stubble' in features:
        result += _path('M36 81 l2 6 M45 88 l2 6 M54 91 l2 6 M64 92 l1 6 M74 91 l-1 6 M83 88 l-2 6 M92 81 l-2 6',width=1.5)
    if 'goatee' in features:
        result += _path('M52 91 L76 91 L69 110 L59 110Z','{fill}')
    if 'sideburns' in features:
        result += _path('M25 38 L34 41 L35 71 L27 66 M103 38 L94 41 L93 71 L101 66','{fill}')
    if 'breath' in features:
        result += _circle(64,82,10,'{accent}') + _path('M85 83 Q103 75 118 81 M89 92 Q109 90 120 99',stroke='{fill}',width=3)
    if 'licking-lips' in features:
        result += _path('M57 85 L57 75 Q68 59 75 75 L75 85Z','#f596aa')
    if 'cross-eyes' in features:
        result += _path('M36 47 L58 47 M47 36 L47 58 M70 47 L92 47 M81 36 L81 58',stroke='{accent}',width=4)
    if 'flat-closed' in features:
        result += _path('M32 54 L60 54 M68 54 L96 54',stroke='{paper}',width=13) + _path('M34 51 L58 51 M70 51 L94 51',width=3)
    if 'wide-eyes' in features:
        result += _circle(47,54,11,'{paper}') + _circle(81,54,11,'{paper}') + _circle(47,54,4,'{ink}') + _circle(81,54,4,'{ink}')
    if 'wink' in features:
        result += _path('M34 54 L60 54',stroke='{paper}',width=13) + _path('M35 52 Q47 62 58 52',width=3)
    if 'freckles' in variant or 'mole' in variant:
        for x, y in ((35,67),(40,72),(44,66),(84,66),(89,72),(94,67)) if 'freckle' in variant else ((85,76),):
            result += _circle(x,y,2,'{ink}','none')
    if 'scar' in variant:
        result += _path('M33 34 L48 73 M30 43 L42 40 M35 58 L47 55', stroke='#bc7777', width=2)
    return result


def pose_diagram(variant: str, features: set[str]) -> str:
    result = _person(pose=variant)
    targets = dict(BODY_LOCATIONS, pocket=(73,73))
    for part, (x,y) in targets.items():
        if ('on_own_'+part) in variant or ('in_'+part) in variant or ('to_'+part) in variant:
            result += _circle(x,y,9,'{accent}') + _arrow(101,58,x,y)
    if variant.startswith('holding') or variant in {'grabbing', 'carrying', 'mouth_hold'}:
        result += _rect(20,56,19,25,'{accent}') + _path('M35 75 L51 52', width=5)
    if any(v in variant for v in ('running','walking','jump','floating','flying','trembling')):
        result += _arrow(8,97,25,76) + _path('M104 105 l13 -5 M103 113 l12 -1', stroke='{accent}')
    if 'bound' in variant or 'restrained' in variant:
        result += _path('M43 52 L85 52 M43 61 L85 61', stroke='{accent}', width=5)
    return result


def body_diagram(variant: str, features: set[str]) -> str:
    result = _person()
    marker = next((xy for part,xy in BODY_LOCATIONS.items() if variant.endswith(part) or variant == part),
                  next((xy for part,xy in BODY_LOCATIONS.items() if part in variant), (64,60)))
    radius = 13 if any(v in variant for v in ('large','huge','thick','wide')) else 6 if any(v in variant for v in ('small','flat','thin')) else 9
    if variant in {'muscular','muscular_male','toned','curvy'}:
        result += _path('M48 45 L42 56 L47 68 L53 72 M80 45 L86 56 L81 68 L75 72', stroke='{accent}', width=6)
    if 'skin' in variant and ('dark' in variant or 'tan' in variant or 'pale' in variant or 'white' in variant or 'colored' in variant):
        result = result.replace('{paper}','{skin}').replace('{fill}','{paper}').replace('{skin}','{fill}')
        result += _rect(97,11,24,35,'{fill}')
    elif variant == 'skin':
        result = result.replace('{paper}','{skin}').replace('{fill}','{paper}').replace('{skin}','{fill}')
        result += _rect(97,11,24,35,'{fill}')
    elif 'breast' in variant or 'pectoral' in variant:
        result += _circle(56,53,radius,'{fill}') + _circle(73,53,radius,'{fill}')
        if 'between' in variant:
            result += _circle(64,53,3,'{accent}','none') + _arrow(100,28,65,47)
    elif 'gap' in variant:
        result += _arrow(38,87,55,87) + _arrow(90,87,73,87)
    else:
        result += _circle(*marker,radius,'{accent}')
    if 'tattoo' in variant:
        result += _star(*marker,7,'{ink}')
    if 'scar' in variant or 'mark' in variant:
        x,y=marker; result += _path(f'M{x-6} {y-7} l12 14 m-10 -4 l8 -5', stroke='#bc7777', width=2)
    if 'mole' in variant:
        result += _circle(*marker,3,'{ink}','none')
    if 'bandaid' in variant or 'bandaged' in variant:
        x,y=marker
        result += _rect(x-9,y-4,18,8,'{paper}',2) + _rect(x-3,y-3,6,6,'{fill}',1)
    if 'hair' in variant:
        x,y=marker; result += _path(f'M{x-6} {y+3} l2 -8 m3 8 l2 -10 m3 10 l2 -8', width=2)
    return result


def _detail_geometry(body: str, shape: str, variant: str, features: set[str], shapes: dict[str,str]) -> str:
    """Visible distinctions for garment details, locations and small scenes."""
    if 'both-eyes' in features:
        body = _circle(64,65,45,'{paper}') + _rect(15,47,98,27,'{fill}')
    if 'no-headband' in features:
        body = _circle(64,62,41,'{paper}') + _rect(8,46,22,45,'{fill}') + _rect(98,46,22,45,'{fill}')
    if 'round-ears' in features:
        body = _circle(31,51,26,'{fill}') + _circle(97,51,26,'{fill}') + _circle(31,51,14,'{paper}') + _circle(97,51,14,'{paper}')
    if 'antennae' in features:
        body = _path('M47 116 Q59 51 18 15 M81 116 Q69 51 110 15',stroke='{fill}',width=5) + _circle(18,15,7,'{accent}') + _circle(110,15,7,'{accent}')
    if 'fins' in features:
        body = _path('M15 114 Q19 34 110 13 L94 108Z','{fill}') + _path('M27 104 L97 33 M38 108 L103 55 M55 108 L102 80',width=2)
    if 'dragon-tail' in features:
        body += _path('M30 35 L20 11 L46 24 L48 2 L66 23 L80 9 L92 34 L111 31 L116 58','{accent}')
    if 'sharp-nails' in features:
        body += _path('M37 26 L43 11 L49 26 M50 15 L56 1 L62 15 M62 23 L69 8 L75 23','{accent}')
    if 'nail-polish' in features:
        body = _path('M28 12 L83 12 L79 72 Q125 73 109 114 L18 114 L21 80Z','{paper}') + _rect(80,88,20,16,'{fill}')
    if 'joints' in features:
        body = _person() + ''.join(_circle(x,y,5,'{accent}') for x,y in ((39,65),(89,65),(51,96),(77,96),(50,45),(78,45)))
    if 'crease' in features:
        body += _path('M42 44 L53 53 L46 59',stroke='{ink}',width=2)
    if 'tanlines' in features:
        body = _person() + _rect(54,45,20,20,'#b78461') + _path('M54 48 L74 48 M54 60 L74 60',stroke='{paper}',width=4)
    if 'triangle' in features or 'sport' in features and shape == 'bra':
        body = shapes['bikini'].split('<path d="M27 79')[0] if 'triangle' in features else _path('M27 30 L44 18 L51 33 L77 33 L84 18 L101 30 L92 83 L36 83Z','{fill}')
    if 'string' in features or 'thong' in features:
        body = _path('M19 38 Q64 58 109 38',stroke='{fill}',width=6) + _path('M48 49 L80 49 L65 105Z','{fill}')
    if 'side-tie' in features:
        body += _path('M22 40 l-14 -12 l3 19 l13 -2 M106 40 l14 -12 l-3 19 l-13 -2','{accent}')
    if 'bandeau' in features:
        body = _rect(19,41,90,37,'{fill}')
    if 'thin-straps' in features:
        body += _path('M48 7 L48 35 M80 7 L80 35',stroke='{paper}',width=6) + _path('M48 7 L48 35 M80 7 L80 35',stroke='{fill}',width=2)
    if 'partial-fingerless' in features:
        body += _path('M38 30 L48 30 M51 20 L61 20',stroke='{paper}',width=10)
    if 'open-foot' in features:
        body = _path('M38 10 L87 10 L91 108 L33 108Z','{fill}')
    if 'layered' in features:
        body += _path('M22 54 L48 54 M80 54 L106 54',stroke='{accent}',width=9)
    if 'garter' in features:
        body = _rect(17,24,94,18,'{fill}') + _path('M32 41 L28 116 M96 41 L100 116',stroke='{fill}',width=6) + _rect(22,98,12,19,'{accent}') + _rect(94,98,12,19,'{accent}')
    if 'shoulder-strap' in features:
        body += _path('M23 53 Q-9 2 80 13 L105 64',stroke='{accent}',width=5)
    if 'chest-pocket' in features:
        body += _rect(71,50,16,18,'{accent}',1)
    if 'epaulettes' in features:
        body += _path('M23 35 L42 22 M86 22 L105 35',stroke='{accent}',width=9)
    if 'lapels' in features or 'kimono-lapel' in features:
        body += _path('M46 16 L61 50 L45 66 M82 16 L67 50 L83 66','{accent}')
    if 'hoop' in features:
        body = _circle(64,70,42,'none') + _path('M55 24 L64 9 L73 24',width=4)
    if 'stud' in features:
        body = _circle(64,64,18,'{fill}') + _path('M64 44 L64 14',stroke='{accent}',width=6)
    if 'circlet' in features:
        body = _circle(64,63,44,'{paper}') + _path('M22 44 Q64 21 106 44',stroke='{fill}',width=6) + _star(64,34,11,'{accent}')
    if 'red-frame' in features:
        body = body.replace('{ink}', '#dd646a')
    if 'tinted' in features:
        body = body.replace('{paper}', '{fill}')
    if 'under-rim' in features:
        body = _path('M10 57 Q10 89 50 87 L54 60 L74 60 L78 87 Q118 89 118 57',stroke='{fill}',width=5)
    if 'glasses' in features:
        body += f'<g transform="translate(25 35) scale(.61)">{shapes["glasses"]}</g>'
    if 'visor' in features:
        body = _path('M20 73 Q64 30 107 73 L114 100 Q64 69 14 100Z','{fill}')
    if 'badge' in features:
        body += _star(64,47,13,'{accent}')
    if 'mini' in features:
        body = _circle(64,74,38,'{paper}') + f'<g transform="translate(23 -3) scale(.45)">{body}</g>'
    if 'veil' in features:
        body += _path('M37 9 Q64 -2 91 9 L113 119 L15 119Z','none',stroke='{accent}',width=2)
    if 'apron' in features:
        body += _path('M51 24 L77 24 L81 62 L93 109 L35 109 L47 62Z','{paper}')
    if 'hair-position' in features or 'hat-position' in features:
        body = _path('M21 105 Q8 16 64 13 Q120 16 107 105Z','{paper}') + f'<g transform="translate(38 13) scale(.46)">{body}</g>'
    if 'ankle-position' in features:
        body = _path('M51 7 L82 7 L78 94 L112 106 L112 120 L37 120 L35 102 L48 90Z','{paper}') + _path('M42 88 L81 88',stroke='{fill}',width=6)
    if 'back-position' in features:
        body = _person() + f'<g transform="translate(42 42) scale(.36)">{body}</g>'
    if 'pin' in features:
        body += _path('M15 68 Q64 1 109 68',stroke='{accent}',width=5)
    if 'wave' in features:
        body = _person(pose='arm_up') + _arrow(10,19,22,6) + _arrow(35,4,48,13)
    if 'double-v' in features:
        hand = _path('M34 115 L31 73 L38 67 L32 17 L42 15 L53 64 L62 15 L73 17 L67 72 Q108 73 96 115Z','{fill}')
        body = f'<g transform="translate(0 15) scale(.6)">{hand}</g><g transform="translate(63 15) scale(.6)">{hand}</g>'
    if 'paw-pose' in features or 'claw-pose' in features:
        body = _path('M26 111 L20 65 Q14 32 33 35 L42 54 Q25 18 45 21 L59 49 Q50 12 70 16 L79 48 Q80 22 99 30 L111 73 L104 114Z','{fill}')
    if 'knees-together' in features:
        body = _person(pose='standing') + _path('M51 96 L77 96',stroke='{paper}',width=10) + _path('M58 73 L64 96 L38 116 M70 73 L64 96 L90 116',width=5)
    if 'weight-shift' in features:
        body = _person(pose='standing_on_one_leg') + _path('M51 39 L78 45 M55 74 L72 70',stroke='{accent}',width=4)
    if 'fighting' in features:
        body = _person(pose='legs_apart') + _path('M50 45 L34 49 L36 31 M78 45 L94 50 L97 28',width=6) + _circle(36,31,7,'{fill}') + _circle(97,28,7,'{fill}')
    if 'back-view' in features:
        body = _person() + _path('M64 41 L64 70',stroke='{accent}',width=2)
    if 'mouth-cover' in features:
        body = _person(pose='hand_on_own_mouth') + _circle(64,28,8,'{accent}')
    if 'head-rest' in features:
        body = _person(pose='hand_on_own_cheek') + _rect(29,47,28,13,'{accent}')
    if 'back-hug' in features or 'back-grab' in features:
        body = _person(50,30,.7) + _person(76,30,.7) + _path('M40 50 Q90 41 88 65 L56 67',stroke='{accent}',width=5)
    if 'matching' in features:
        body = _person(34,30,.65) + _person(94,30,.65)
    if 'selfie' in features:
        body += _circle(64,48,12,'{fill}') + _path('M44 77 Q43 62 64 62 Q85 62 84 77Z','{fill}')
    if 'reach' in features:
        body += _arrow(16,108,55,81)
    if 'bouquet' in features:
        body = ''.join(f'<g transform="translate({x} {y}) scale(.42)">{shapes["flower"]}</g>' for x,y in ((12,7),(52,7),(33,38))) + _path('M38 78 L60 120 L91 78Z','{paper}')
    if 'sunflower' in features:
        body = shapes['flower'].replace('{fill}', '#f1ce61').replace('{accent}', '#926447')
    if 'rose' in features:
        body = _circle(64,52,35,'{fill}') + _path('M44 39 Q72 16 82 44 Q99 69 66 80 Q36 88 36 58 Q33 38 60 40 Q82 39 70 63 Q50 77 48 56 Q50 44 64 51',width=2) + _path('M64 87 L64 121 M64 104 Q88 83 100 99 Q86 114 64 109',stroke='{accent}',width=5)
    if 'petals' in features:
        body = ''.join(f'<g transform="rotate({a} {x} {y})">{_path(f"M{x} {y-12} Q{x-15} {y} {x} {y+13} Q{x+15} {y} {x} {y-12}Z","{fill}")}</g>' for x,y,a in ((23,24,20),(78,22,-20),(50,66,60),(106,72,90),(28,111,-30)))
    if 'grass' in features:
        body = _path('M22 118 L8 45 L42 100 L51 15 L64 101 L80 35 L81 108 L117 61 L107 118Z','{fill}')
    if 'curved' in features:
        body = _path('M27 96 Q83 72 95 9 Q118 64 42 110Z','{fill}') + _path('M41 104 L19 123 M20 91 L51 113',stroke='{accent}',width=7)
    if 'curtains' in features:
        body += _path('M12 10 L45 10 Q39 53 22 79 L46 117 L12 117Z M116 10 L83 10 Q89 53 106 79 L82 117 L116 117Z','{accent}')
    if 'book' in features:
        body += f'<g transform="translate(54 18) scale(.45)">{shapes["book"]}</g>'
    if 'cowboy' in features:
        body = _rect(12,8,104,112,'{paper}') + '<defs><clipPath id="cowboy-crop"><rect x="15" y="9" width="98" height="95"/></clipPath></defs>' + f'<g clip-path="url(#cowboy-crop)">{_person(64,18,.94)}</g>' + _path('M14 104 L114 104',stroke='{accent}',width=5)
    if 'behind' in features:
        body += _path('M75 41 L75 72',stroke='{accent}',width=3) + _path('M61 19 Q75 36 89 19',width=3)
    if 'side' in features and shape == 'portrait':
        body = _path('M48 13 Q107 13 91 51 L108 66 L92 73 L92 88 L75 94 L72 119 L30 119 L40 86 Q14 34 48 13Z','{paper}') + _circle(83,51,3,'{ink}')
    if 'pov' in features:
        body += f'<g transform="translate(7 91) scale(.23)">{shapes["hand"]}</g><g transform="translate(90 91) scale(.23)">{shapes["hand"]}</g>'
    if 'border' in features or 'outline' in features:
        body += _rect(5,5,118,118,'none',0)
    if 'rim' in features:
        body = _circle(64,60,50,'{accent}') + _person(64,25,.78).replace('{ink}','{accent}')
    if 'sketch' in features:
        body = _rect(9,9,110,110,'{paper}') + _path('M21 76 Q60 4 94 47 Q120 75 63 109 M33 95 L105 42 M37 105 L113 53',stroke='{fill}',width=1) + f'<g transform="translate(67 67) scale(.4)">{shapes["pen"]}</g>'
    if 'watermark' in features:
        body = shapes['frame'] + '<g opacity=".7">' + _text('©',64,85,55) + '</g>'
    if 'drop' in features:
        body += _path('M80 82 Q65 99 80 104 Q94 99 80 82Z','#67bde3',width=1)
    if 'sheath' in features:
        body = _path('M35 113 L76 23 L90 30 L49 119Z','{fill}') + _path('M70 20 L94 31',stroke='{accent}',width=6)
    if 'heels' in features:
        body += _path('M29 106 L24 125 L38 125 L44 111Z','{fill}')
    if 'strap' in features:
        body += _path('M35 72 L84 84',stroke='{accent}',width=7)
    if 'tucked' in features:
        body += _path('M35 91 L94 91 L94 121 L72 121 L65 104 L57 121 L35 121Z','{accent}')
    if 'slip' in features:
        body += _arrow(108,46,108,87)
    if 'gap' in features:
        body += _rect(59,48,10,43,'{paper}',0)
    if 'steam' in features or 'wine-glass' in features:
        body += (_path('M46 19 Q36 9 46 1 M67 19 Q57 9 67 1',stroke='{accent}',width=2) if 'steam' in features else _path('M101 83 L101 114 M89 119 L113 119 M88 64 Q101 99 114 64Z','{paper}'))
    if 'straw' in features:
        body += _path('M65 89 L74 8 L95 8',stroke='{accent}',width=4)
    if 'blank' in features:
        body = _rect(19,9,90,111,'{paper}')
    if 'wood' in features:
        body += _path('M29 59 q8 -5 18 0 M76 98 q9 -5 21 0',stroke='{accent}',width=2)
    if 'sand' in features:
        body += ''.join(_circle(x,y,1.5,'{accent}','none') for x,y in ((19,84),(43,75),(53,98),(75,68),(98,93),(85,108)))
    if features & {'sunset', 'sunrise', 'horizon'}:
        body = _path('M8 83 L120 83 M9 106 L119 106',stroke='{fill}',width=4)
        if 'horizon' not in features:
            body += _path('M38 82 A26 26 0 0 1 90 82Z','#e89954') + _arrow(106,48 if 'sunset' in features else 76,106,76 if 'sunset' in features else 48)
    if 'half-person' in features:
        body = _person() + _rect(10,65,108,52,'{fill}') + _path('M10 65 Q24 55 37 65 Q51 75 65 65 Q79 55 94 65 Q108 75 118 65',width=2)
    if features & {'panels-2','panels-3','panels-4'}:
        count = 2 if 'panels-2' in features else 3 if 'panels-3' in features else 4
        body = ''.join(_rect(11,6+i*116/count,106,108/count,'{paper}',0)+_circle(42,6+(i+.5)*116/count,7,'{fill}') for i in range(count))
    if 'outside' in features or 'foot-crop' in features or 'head-crop' in features:
        y = -12 if 'head-crop' in features else 21
        body = _rect(17,16,94,96,'{paper}',0) + '<defs><clipPath id="tag-crop"><rect x="19" y="18" width="90" height="92"/></clipPath></defs>'
        body += f'<g clip-path="url(#tag-crop)">{_person(64,y,1.1)}</g>' + _arrow(117,95,101,95 if y>=0 else 18)
    if 'pov-hands' in features:
        hand = shapes['hand']
        body = f'<g transform="translate(0 41) scale(.6)">{hand}</g><g transform="translate(128 41) scale(-.6 .6)">{hand}</g>'
    if 'foreground' in features or 'motion' in features:
        body += _path('M7 100 L40 100 M90 102 L121 102',stroke='{accent}',width=12 if 'foreground' in features else 5)
    if 'zoom' in features:
        body += _circle(93,32,25,'{paper}') + _star(93,32,15,'{accent}') + _arrow(55,76,75,49)
    if 'emphasis' in features or 'rays' in features:
        body += ''.join(_path(f'M{x} {y} L{64+(x-64)*.65} {64+(y-64)*.65}',stroke='{accent}',width=3) for x,y in ((4,4),(64,4),(124,4),(4,64),(124,64),(4,124),(64,124),(124,124)))
    if 'chromatic' in features:
        body = _circle(57,63,40,'none',stroke='#dd646a') + _circle(66,63,40,'none',stroke='#579bd4') + _circle(72,63,40,'none',stroke='#6aa780')
    if 'chinese' in features or 'korean' in features or 'japanese' in features:
        body = _rect(10,15,108,97,'{paper}') + _text('字' if 'chinese' in features else '한' if 'korean' in features else 'あ',64,87,56)
    if 'sound-effects' in features:
        body = _star(64,64,55,'{paper}') + _text('!',64,90,62)
    if 'question-exclamation' in features:
        body = _text('!?',64,95,75)
    if 'page-number' in features:
        body = _rect(10,15,108,97,'{paper}') + _text('12',64,101,24)
    if 'name-tag' in features:
        body = _rect(9,26,110,70,'{paper}') + _circle(30,54,12,'{fill}') + _path('M18 79 Q30 60 42 79 M57 48 L103 48 M57 65 L91 65',width=3)
    if 'vertical-text' in features:
        body = _rect(44,7,40,114,'{paper}') + _text('札',64,77,29)
    if 'gift' in features or 'confetti' in features or 'pen' in features:
        secondary = shapes['gift' if 'gift' in features else 'confetti' if 'confetti' in features else 'pen']
        body += f'<g transform="translate(69 69) scale(.43)">{secondary}</g>'
    if 'halo' in features:
        body += '<ellipse cx="64" cy="13" rx="27" ry="8" fill="none" stroke="{accent}" stroke-width="4"/>'
    if 'mask' in features:
        body += _rect(32,69,64,30,'{fill}')
    if 'nun' in features:
        body = _path('M15 120 L17 50 Q12 7 64 8 Q116 7 111 50 L113 120Z','{fill}') + _circle(64,64,31,'{paper}') + _path('M24 27 L104 27',stroke='{paper}',width=13)
    if 'miko' in features:
        body = body.replace('{fill}','{paper}') + _path('M39 70 L89 70 L103 120 L25 120Z','#dd646a')
    if 'cheer' in features:
        body = _person(pose='arms_up') + f'<g transform="translate(8 0) scale(.3)">{shapes["pom_pom"]}</g><g transform="translate(82 0) scale(.3)">{shapes["pom_pom"]}</g>'
    if 'santa' in features:
        body = body.replace('{fill}', '#dd646a') + _path('M42 111 L86 111 M26 78 L39 78 M89 78 L102 78',stroke='{paper}',width=8)
    if 'double-buttons' in features:
        body += ''.join(_circle(x,y,3,'{accent}','none') for x in (54,74) for y in (54,72,90))
    if 'on-shoulders' in features:
        body = f'<g transform="translate(32 29) scale(.52)">{body}</g>' + _person()
    if 'thumbs-up' in features:
        body = _path('M35 117 L33 64 L49 48 L57 13 Q68 1 73 17 L69 53 L100 55 Q113 55 109 76 L97 115Z','{fill}')
    if 'salute' in features:
        body = _person() + _path('M78 45 L101 35 L76 19',width=6)
    if 'dance' in features:
        body = _person(pose='standing_on_one_leg') + _path('M50 45 L21 29 M78 45 L106 13',width=5) + f'<g transform="translate(86 61) scale(.25)">{shapes["music"]}</g>'
    if 'wrists-bound' in features:
        body = _person(pose='crossed_arms') + _rect(52,53,26,13,'{accent}')
    if 'back-to-back' in features:
        body = _person(51,30,.68) + _person(77,30,.68) + _path('M63 36 L63 70',stroke='{accent}',width=4)
    if 'electric' in features:
        body += _path('M47 81 L76 88',stroke='{accent}',width=6)
    if 'axes' in features:
        body += _arrow(20,99,20,14) + _arrow(20,99,118,99)
    if 'grain' in features:
        body += ''.join(_circle(x,y,1.4,'{accent}','none') for x,y in ((24,21),(49,31),(75,19),(95,52),(23,81),(46,91),(83,110),(110,97),(62,61),(32,109),(79,77),(110,24)))
    if 'wide-shot' in features:
        body = _rect(9,9,110,110,'{paper}') + _person(64,70,.35) + _path('M16 93 L37 67 L56 90 M79 83 L94 64 L113 86',stroke='{accent}',width=3)
    if 'extra-limbs' in features:
        body = _person() + _path('M50 54 L26 49 M78 54 L104 49',stroke='{accent}',width=5)
    if 'extra-fingers' in features:
        body += _path('M78 38 L100 14 L112 18 L96 57Z','{accent}')
    if 'missing-fingers' in features:
        body = _path('M29 115 L26 72 L34 66 L32 31 L43 27 L51 65 L58 17 L70 18 L68 67 L91 63 L100 80 L97 115Z','{fill}')
    if 'flat-diamond' in features:
        body = _path('M64 5 L118 64 L64 123 L10 64Z','{fill}')
    return body


@lru_cache(maxsize=8)
def _load_primitives(directory: Path) -> dict[str, str]:
    payload = json.loads((directory / 'primitives.json').read_text(encoding='utf-8'))
    if payload.get('schema_version') != 1 or not isinstance(payload.get('shapes'), dict):
        raise ValueError('图示素材版本或格式无效')
    if any(not isinstance(k,str) or not isinstance(v,str) for k,v in payload['shapes'].items()):
        raise ValueError('图示素材必须是 SVG 文字')
    return payload['shapes']


def compose_svg(visual: TagVisual, directory: Path, *, ink: str = '#263443', paper: str = '#f5f6fa', preview: bool = False) -> str:
    if not visual.has_icon:
        return ''
    recipe = visual.recipe or {}
    shapes = _load_primitives(directory)
    shape = str(recipe['shape'])
    if shape not in shapes:
        raise ValueError(f'缺少图示基础形状：{shape}')
    variant = str(recipe.get('variant', visual.key.replace(' ', '_')))
    features = set(recipe.get('features', ()))
    family = str(recipe.get('family', 'object'))
    if family == 'hair':
        body = hair_diagram(variant, features)
    elif family == 'eyes':
        body = eyes_diagram(variant, features)
    elif family == 'face':
        body = face_diagram(variant, features)
    elif family == 'pose':
        body = pose_diagram(variant, features)
        if recipe.get('support_shape'):
            support = shapes[str(recipe['support_shape'])]
            body = f'<g transform="translate(20 5) scale(.7)">{support}</g>' + _person(65,11,.8,variant)
    elif family == 'body':
        body = body_diagram(variant, features)
    else:
        body = shapes[shape]
    body = _detail_geometry(body, shape, variant, features, shapes)
    if recipe.get('refinement') == 'r1':
        from app.tag_visual_refinements import refined_geometry
        drawing = refined_geometry(visual.key, shape, variant, features, shapes)
        if drawing is None:
            raise ValueError(f'缺少已登记的重制图示：{visual.key}')
        body = drawing.body
        features.difference_update(drawing.consumed)
    if 'border' in features:
        body += '<rect x="10" y="10" width="108" height="108" fill="none" stroke="{fill}" stroke-width="6"/>'
    if 'outline' in features:
        body = _circle(64,64,45,'{ink}') + '<circle cx="64" cy="64" r="42" fill="none" stroke="{fill}" stroke-width="6"/>'
    if 'object-pattern' in features:
        pattern = shapes[str(recipe['pattern_shape'])]
        body = _rect(9,9,110,110,'{paper}',0) + ''.join(f'<g transform="translate({x} {y}) scale(.28)">{pattern}</g>' for x in (14,49,84) for y in (14,49,84))
    if 'on-body' in features:
        tx,ty = BODY_LOCATIONS.get(str(recipe.get('part')), (64,51))
        body = _person() + f'<g transform="translate({tx-21} {ty-21}) scale(.33)">{body}</g>' + _arrow(111,ty,tx+17,ty)
    if 'touch-other' in features:
        tx,ty = BODY_LOCATIONS.get(str(recipe.get('part')), (64,51))
        x,y = 91+(tx-64)*.65, 30+(ty-21)*.65
        body += _path(f'M46 58 L{x} {y}',stroke='{accent}',width=4) + _circle(x,y,6,'{accent}')
    if 'mouth-held' in features:
        body += _circle(21,26,17,'{paper}') + _circle(16,23,2,'{ink}','none') + _path('M28 29 L39 29',width=4)
    if 'unworn' in features:
        body += _path('M50 12 Q61 0 66 10 L64 16 L102 35 L26 35Z',stroke='{accent}',width=3)
    if shape == 'sleeves' and 'short' in features:
        body = _path('M24 22 L52 28 L48 65 L18 60Z M104 22 L76 28 L80 65 L110 60Z','{fill}')
    if shape == 'skirt' and 'pencil' in features:
        body = _path('M39 24 L89 24 L85 112 L43 112Z','{fill}') + _path('M42 37 L86 37',width=2)
    if 'sleeveless' in features and shape == 'dress':
        body = _path('M48 13 L57 16 L64 28 L71 16 L80 13 L76 57 L108 114 Q64 123 20 114 L52 57Z','{fill}')
    if 'strapless' in features and shape in {'dress','leotard'}:
        body = _path('M43 36 Q64 49 85 36 L76 57 L106 114 Q64 122 22 114 L52 57Z','{fill}') if shape=='dress' else _path('M40 31 Q64 42 88 31 L78 52 L88 75 L64 103 L40 75 L50 52Z','{fill}')
    if 'off-shoulder' in features:
        if shape == 'dress':
            body = _path('M22 35 L46 37 Q64 51 82 37 L106 35 L103 62 L87 62 L76 64 L107 114 Q64 123 21 114 L52 64 L41 62 L25 62Z','{fill}')
            body += _path('M48 66 L80 66', width=2)
        else:
            body = _path('M18 43 L45 44 L48 56 L80 56 L83 44 L110 43 L102 80 L87 79 L87 113 L41 113 L41 79 L26 80Z','{fill}')
    if 'puffy' in features and shape=='sleeves':
        body = _path('M27 23 Q-1 26 14 70 L23 109 L45 112 L44 69 Q63 35 27 23Z M101 23 Q129 26 114 70 L105 109 L83 112 L84 69 Q65 35 101 23Z','{fill}')
    if 'fingerless' in features and shape=='gloves':
        body = shapes['gloves'] + _path('M40 40 L81 40',stroke='{paper}',width=13)
    if 'collared' in features or 'sailor' in features:
        body += _path('M44 26 L63 43 L48 60 L38 32 M84 26 L65 43 L80 60 L90 32','{paper}')
        if 'sailor' in features:
            body += _path('M40 29 L63 45 L51 62 M88 29 L65 45 L77 62',stroke='{accent}',width=3)
    if 'dark-lenses' in features:
        body = shapes['glasses'].replace('{paper}','{fill}')
    if 'black-frame' in features:
        body = body.replace('{ink}', '#353944')
    if 'pleated' in features:
        body += _path('M49 44 L36 100 M59 44 L55 107 M69 44 L73 107 M79 44 L92 100',width=2)
    if 'high-collar' in features:
        body += _rect(51,12,26,25,'{fill}')
    if 'highleg' in features:
        body += _path('M40 75 L57 58 M88 75 L71 58',stroke='{paper}',width=6)
    if 'halterneck' in features:
        body += _path('M45 26 L62 8 L66 8 L83 26',stroke='{fill}',width=7)
    if 'side-slit' in features:
        body += _path('M88 69 L88 114',stroke='{paper}',width=9)
    if 'buttons' in features or 'corset' in features or 'zipper' in features:
        for y in (47,59,71,83,95):
            body += _circle(64,y,3,'{accent}','none')
        if 'zipper' in features: body += _path('M63 34 L63 110',width=2)
        if 'corset' in features: body += _path('M53 42 L75 54 L53 66 L75 78 L53 90',width=2)
    if 'pockets' in features:
        body += _rect(42,61,18,21,'{accent}') + _rect(69,61,18,21,'{accent}')
    if 'denim' in features or 'knit' in features:
        for p in (50,62,74,86): body += _path(f'M43 {p} l12 5 l12 -5 l12 5',stroke='{accent}',width=1)
    if 'cross' in features:
        body += _path('M42 43 L86 87 M42 87 L86 43',stroke='{accent}',width=7)
    if 'bow' in features:
        body += f'<g transform="translate(43 28) scale(.34)">{shapes["bow"]}</g>'
    if 'gold-trim' in features or 'ribbon-trim' in features:
        body += _path('M41 108 L87 108',stroke='#d9b85d' if 'gold-trim' in features else '{accent}',width=5)
    if 'color-trim' in features:
        body += _path('M41 108 L87 108 M31 63 L43 54 M97 63 L85 54',stroke='{accent}',width=5)
    if 'cutout' in features:
        body += _circle(65,50,11,'{paper}')
    if 'shoulder' in features:
        body += _path('M38 33 L49 31 M79 31 L90 33',stroke='{paper}',width=9)
    if 'armor' in features:
        body += _path('M37 38 L82 38 M36 60 L81 60 M35 82 L80 82',stroke='{accent}',width=6)
    if 'lowleg' in features:
        body += _path('M37 65 L92 65 L86 92 L64 103 L42 92Z','{fill}')
    if 'open-toes' in features:
        body += _path('M29 111 L109 111',stroke='{paper}',width=12)
    if 'wide' in features: body=f'<g transform="translate(-12 0) scale(1.2 1)">{body}</g>'
    if 'extra' in features or 'multiple' in features:
        body=f'<g transform="translate(6 4) scale(.75)">{body}</g>' + f'<g transform="translate(65 65) scale(.4)">{body}</g>'
    if 'claws' in features:
        body += _path('M40 27 L40 10 L49 24 M53 17 L57 1 L61 17 M67 21 L76 4 L75 26','{paper}')
    if 'floppy' in features:
        body = _path('M30 105 Q-3 12 35 19 L54 77 M98 105 Q131 12 93 19 L74 77','{fill}')
    if 'fox' in features or 'fluffy' in features:
        body += _path('M97 86 L104 78 L112 88 L105 92 L114 101 L99 112 L92 100','{paper}',width=2)
    if 'spade' in features:
        body += _path('M45 20 L21 4 L4 23 L26 37Z','{accent}')
    if 'fake' in features:
        body += _path('M16 100 L43 117 M111 100 L85 117',stroke='{accent}',width=4)
    if any(v in features for v in ('cat-ears','fox-ears','wolf-ears','horse-ears','rabbit-ears','pointy-ears')):
        body += f'<g transform="translate(38 2) scale(.4)">{shapes["rabbit_ears" if "rabbit-ears" in features else "ears"]}</g>'
    if 'horns' in features: body += f'<g transform="translate(40 -2) scale(.4)">{shapes["horns"]}</g>'
    if 'magic' in features: body += _star(100,41,17,'{accent}')
    if 'person' in features and shape in {'cat','dog','rabbit'}:
        body=f'<g transform="translate(26 0) scale(.6)">{body}</g>' + _person(64,52,.59)
    elif 'person' in features:
        body += _person(75,44,.5)
    if 'held' in features:
        body += f'<g transform="translate(2 62) scale(.4)">{shapes["hand"]}</g>'
    if 'gaze' in features or 'head-touch' in features:
        body += _arrow(38,40,87,40)
    if 'family' in features:
        body += _path('M30 101 L30 115 L98 115 L98 101 M64 115 L64 122',stroke='{accent}',width=3)
    if 'close' in features:
        body += _path('M33 65 Q64 42 95 65',stroke='{accent}',width=6)
    if 'male-female' in features or 'female-female' in features or 'male-male' in features:
        signs=('♂','♀') if 'male-female' in features else ('♀','♀') if 'female-female' in features else ('♂','♂')
        body += _text(signs[0],25,122,22)+_text(signs[1],103,122,22)
    if 'child' in features or 'chibi' in features:
        body=_person(36,12,.89)+_person(97,49,.51) if 'child' in features else _circle(64,34,28,'{paper}')+_person(64,55,.5)
    if 'gender' in features: body += _text('♂↔♀',64,125,20)
    if 'focus' in features: body += _circle(64,63,53,'none')
    if 'toy' in features: body += _path('M35 95 L42 88 M40 101 L47 94',stroke='{accent}',width=3)
    if 'excluded' in features or 'clothes-removed' in features:
        body += _path('M10 112 L116 10',stroke='#dd646a',width=7)
    if 'compare' in features:
        body=f'<g transform="translate(1 20) scale(.42)">{body}</g><g transform="translate(73 20) scale(.42)">{body}</g>' + _arrow(50,66,73,66)
    if 'age-difference' in features or 'height-difference' in features:
        body = _person(37,14,.95) + _person(98,50,.57) + _arrow(13,14,13,115)
    if 'tilt-upside-down' in features:
        body = f'<g transform="rotate(180 64 64)">{body}</g>'
    if 'tilt' in features: body=f'<g transform="rotate(-14 64 64) scale(.9) translate(7 7)">{body}</g>'
    if 'blur' in features: body += _path('M19 38 L37 38 M91 38 L109 38 M19 88 L37 88 M91 88 L109 88',stroke='{accent}',width=9)
    if 'perspective' in features: body += _path('M10 14 L64 64 L118 14 M10 114 L64 64 L118 114',stroke='{accent}',width=2)
    if 'letterbox' in features: body += _rect(9,13,110,20,'{ink}',0)+_rect(9,95,110,20,'{ink}',0)
    if 'mirror' in features: body += _path('M64 7 L64 121',stroke='{accent}',width=4)
    if 'shadow' in features: body += '<g opacity=".65">'+_rect(29,32,70,28,'{ink}',0)+'</g>'
    if 'stars' in features: body += _star(105,29,12,'{accent}')+_star(26,20,8,'{accent}')
    if 'moon' in features: body= _circle(64,64,40,'{fill}')
    if 'thought' in features: body += _circle(32,106,7,'{paper}')+_circle(20,119,4,'{paper}')
    if 'heart' in features: body += f'<g transform="translate(41 30) scale(.38)">{shapes["heart"]}</g>'
    if 'ellipsis' in features: body=(_path('M13 22 L115 22 L115 84 L62 84 L31 112 L36 84 L13 84Z','{paper}') if shape=='speech' else '')+_text('…',64,80,55)
    if 'question' in features: body=_text('?',64,96,88)
    if 'exclamation' in features: body=_text('!',64,96,88)
    if 'url' in features or 'at' in features or 'copyright' in features or 'date' in features:
        body=_rect(10,15,108,97,'{paper}')+_text('@' if 'at' in features else '©' if 'copyright' in features else 'URL' if 'url' in features else '日',64,82,40)
    if 'quality' in features or 'low-quality' in features:
        body=_rect(9,19,110,91,'{paper}')+_star(64,60,31,'{fill}')
        if 'low-quality' in features: body += _arrow(104,35,104,98)
        else: body += _arrow(104,98,104,35)
    if family=='object' and visual.group=='rating':
        grade={'general':'G','sensitive':'S','questionable':'Q','explicit':'E'}
        body=_rect(17,18,94,92,'{fill}')+_text(grade.get(variant,'R'),64,85,55)
    color = str(recipe.get('color', '#92b7d8' if family not in {'hair','eyes'} else '#9b704e'))
    accent = str(recipe.get('accent', '#e99d83'))
    if shape == 'nails':
        accent, color = color, paper
    if 'bandage' in features:
        body = _rect(15,45,98,39,'{paper}',12) + _rect(44,48,40,33,'{fill}',2)
        for x in (25,35,95,105): body += _circle(x,64,2,'{ink}','none')
    if 'hooded' in features:
        body += f'<g transform="translate(40 0) scale(.38)">{shapes["hood"]}</g>'
    if 'loose' in features:
        body = f'<g transform="translate(-7 0) scale(1.11 1)">{body}</g>'
    if 'tight' in features:
        body = f'<g transform="translate(13 0) scale(.8 1)">{body}</g>'
    if 'detached' in features:
        body += _path('M9 31 L47 31 M80 31 L119 31',stroke='{paper}',width=6)
    if 'high-waist' in features:
        body += _path('M35 16 L93 16',stroke='{accent}',width=6)
    if 'ribbed' in features:
        for x in range(44,85,8): body += _path(f'M{x} 46 L{x} 105',stroke='{accent}',width=1.5)
    if 'denim' in features or 'lace-up' in features or 'cross-laced' in features:
        body += _path('M53 43 L75 55 L53 67 L75 79 L53 91 M75 43 L53 55 L75 67 L53 79 L75 91',stroke='{accent}',width=2)
    if 'print' in features:
        body += _star(65,66,16,'{accent}')
    if 'star-pattern' in features or 'heart-pattern' in features:
        for x,y in ((47,53),(78,58),(59,82)):
            body += (_star(x,y,7,'{accent}') if 'star-pattern' in features else f'<g transform="translate({x-8} {y-8}) scale(.14)">{shapes["heart"]}</g>')
    if 'suspender' in features:
        body += _path('M47 12 L53 57 M81 12 L75 57',stroke='{accent}',width=5)
    if 'rimless' in features:
        body = shapes['glasses'].replace('stroke-width="3"','stroke-width="1"')
    if 'head-position' in features:
        body = _circle(64,64,41,'{paper}') + f'<g transform="translate(32 0) scale(.5)">{body}</g>'
    if 'blood' in features:
        body += _path('M54 45 Q36 65 54 72 Q74 64 54 45Z','#dd646a',width=1)
    # Known visual modifiers have visible geometry rather than letter badges.
    if 'striped' in features or 'vertical-striped' in features:
        vertical = 'vertical-striped' in features
        for p in (42,54,66,78,90):
            body += _path(f'M{p} 45 L{p} 94' if vertical else f'M40 {p} L88 {p}', stroke='{accent}', width=3)
    if 'plaid' in features or 'fishnet' in features:
        for p in (44,58,72,86):
            body += _path(f'M{p} 42 L{p} 95 M40 {p} L90 {p}', stroke='{accent}', width=2)
    if 'polka-dot' in features:
        for x,y in ((48,53),(76,53),(62,67),(48,81),(76,81)):
            body += _circle(x,y,3,'{accent}','none')
    if 'floral' in features:
        body += _star(55,58,8,'{accent}') + _star(76,82,8,'{accent}')
    if 'frilled' in features or 'lace' in features or 'fur-trim' in features:
        body += _path('M38 95 q4 10 8 0 q4 10 8 0 q4 10 8 0 q4 10 8 0 q4 10 8 0 q4 10 8 0', stroke='{accent}', width=3)
    if 'open' in features:
        body += _path('M59 43 L54 97 M69 43 L74 97', stroke='{paper}', width=7)
    if 'torn' in features:
        body += _path('M41 68 l10 -4 l-4 10 l13 -8 l-4 12', stroke='{paper}', width=5)
    if 'wet' in features or 'shiny' in features:
        body += _path('M101 33 Q88 54 101 59 Q114 54 101 33Z', '#67bde3', width=1)
    if 'transparent' in features:
        body += _rect(46,52,36,38,'{paper}') + _path('M49 85 L78 57', stroke='{accent}', width=4)
    if 'long' in features:
        body += _arrow(105,43,105,105)
    elif 'short' in features or 'cropped' in features:
        body += _arrow(105,45,105,73)
    if 'lifted' in features or 'pulled' in features:
        body += _arrow(101,95,101,48)
    if 'aside' in features:
        body += _arrow(39,97,104,97)
    if 'single' in features:
        body += _circle(106,105,12,'{paper}') + _text('1',106,111,17)
    if 'checkered' in features:
        body += ''.join(_rect(x,y,12,12,'{accent}',0) for x in (42,54,66,78) for y in (46,58,70,82) if (x+y)%24==16)
    if 'animal-print' in features:
        body += _path('M48 49 q-6 7 1 11 q10 -1 5 -8 M74 70 q-7 4 -2 11 q8 4 11 -4 M49 86 q-6 8 3 10 q7 -4 1 -9','{accent}',stroke='{ink}',width=1)
    if 'leather' in features or 'silk' in features:
        body += _path('M45 42 Q50 68 43 96 M82 42 Q77 68 85 96',stroke='{accent}',width=3 if 'leather' in features else 1)
    if 'low' in features or 'high' in features:
        body += _arrow(113,68,113,106 if 'low' in features else 27)
    if 'asymmetrical' in features:
        body += _path('M44 111 L74 77 L86 111','{paper}')
    if 'blue-theme' in features:
        body = re.sub(r'#[0-9a-fA-F]{6}', '#579bd4', body)
    if 'resolution' in features or 'low-resolution' in features:
        for x in (35,59,83):
            for y in (35,59,83): body += _rect(x,y,13,13,'{accent}',0)
        body += _arrow(112,100 if 'resolution' in features else 26,112,26 if 'resolution' in features else 100)
    if 'rolled' in features:
        body += _path('M21 65 L37 65 M92 65 L108 65', stroke='{accent}', width=7)
    if 'two-tone' in features and family not in {'hair','eyes'}:
        body += '<defs><clipPath id="tag-two-tone"><rect x="64" y="0" width="64" height="128"/></clipPath></defs><g clip-path="url(#tag-two-tone)">' + body.replace('{fill}','{accent}') + '</g>'
    if 'multicolored' in features and family != 'hair':
        body += _path('M26 94 L45 94',stroke='#dd646a',width=7) + _path('M47 94 L67 94',stroke='#6aa780',width=7) + _path('M69 94 L89 94',stroke='#579bd4',width=7)
    if 'gradient' in features or 'gradient' in variant:
        body = body.replace('{fill}', 'url(#tag-gradient)') + '<defs><linearGradient id="tag-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{fill}"/><stop offset="1" stop-color="{accent}"/></linearGradient></defs>'
    if recipe.get('count'):
        count = int(recipe['count'])
        body = ''.join(f'<g transform="translate({i*29+6} 20) scale(.29)">{_person()}</g>' for i in range(min(count,4)))
        body += _text(str(recipe.get('count_label', count)),64,118,22)
    if preview and family in {'body', 'pose'}:
        body += _path('M12 119 L116 119', stroke='{ink}', width=1)
    body = body.replace('{ink}',ink).replace('{paper}',paper).replace('{fill}',color).replace('{accent}',accent)
    if 'greyscale' in features or 'monochrome' in features:
        def grey(match):
            hex_color = match.group()
            rgb = [int(hex_color[i:i+2],16) for i in (1,3,5)]
            value = round(sum(c*w for c,w in zip(rgb,(.2126,.7152,.0722))))
            return '#'+f'{value:02x}'*3
        body = re.sub(r'#[0-9a-fA-F]{6}',grey,body)
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">{body}</svg>'
