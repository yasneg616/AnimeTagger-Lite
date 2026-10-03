"""Rebuild the offline visual catalog and honest per-tag coverage ledger.

This is an explicit development command, never run by the desktop application.
Definitions and drawings are original; Danbooru wiki references document the
tag vocabulary, not copied illustrations or downloaded example photographs.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
from types import MappingProxyType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.prompts.normalizer import canonical_tag_key
from app.tag_visuals import TagVisualLibrary, SEMANTIC_STATUSES
from app.tag_visual_svg import _path as P, _circle as C, _rect as R, _star as S, _text as T, _arrow as A, _person


COLORS = {
    'black': ['黑色', '#353944'], 'white': ['白色', '#ffffff'], 'grey': ['灰色', '#949aa6'], 'gray': ['灰色', '#949aa6'],
    'brown': ['棕色', '#926447'], 'light brown': ['浅棕色', '#c7976b'], 'dark brown': ['深棕色', '#624631'],
    'blonde': ['金色', '#e8c66f'], 'blond': ['金色', '#e8c66f'], 'yellow': ['黄色', '#f1ce61'],
    'red': ['红色', '#dd646a'], 'blue': ['蓝色', '#579bd4'], 'green': ['绿色', '#6aa780'],
    'pink': ['粉色', '#e997bd'], 'purple': ['紫色', '#a48bcf'], 'orange': ['橙色', '#e89954'],
    'aqua': ['青蓝色', '#68c7ca'], 'silver': ['银色', '#bcc4cf'], 'gold': ['金色', '#d9b85d'],
    'dark': ['深色', '#626276'], 'light': ['浅色', '#d8dce6'], 'multicolored': ['多色', '#a48bcf'],
}
MODIFIERS = {
    'striped': ('条纹', 'striped'), 'vertical-striped': ('竖条纹', 'vertical-striped'), 'plaid': ('格纹', 'plaid'),
    'polka dot': ('圆点纹', 'polka-dot'), 'frilled': ('带褶边的', 'frilled'), 'lace-trimmed': ('蕾丝边', 'lace'),
    'torn': ('破损的', 'torn'), 'wet': ('湿的', 'wet'), 'see-through': ('透视材质的', 'transparent'),
    'open': ('敞开的', 'open'), 'long': ('长款', 'long'), 'short': ('短款', 'short'), 'cropped': ('截短款', 'cropped'),
    'sleeveless': ('无袖', 'sleeveless'), 'strapless': ('无肩带', 'strapless'), 'puffy': ('蓬松的', 'puffy'),
    'single': ('单个', 'single'), 'one': ('单个', 'single'), 'floral': ('花卉图案', 'floral'),
    'fur-trimmed': ('毛绒边', 'fur-trim'), 'shiny': ('有光泽的', 'shiny'), 'two-tone': ('双色', 'two-tone'),
    'highleg': ('高开口', 'highleg'), 'detached': ('分离式', 'detached'), 'hooded': ('连帽', 'hooded'),
    'loose': ('宽松', 'loose'), 'tight': ('紧身', 'tight'), 'high-waist': ('高腰', 'high-waist'),
    'checkered': ('棋盘格纹', 'checkered'), 'ribbed': ('罗纹', 'ribbed'), 'denim': ('牛仔布', 'denim'),
    'leather': ('皮革', 'leather'), 'latex': ('乳胶材质', 'shiny'), 'silk': ('丝质', 'silk'),
    'sailor': ('水手领', 'sailor'), 'collared': ('有翻领的', 'collared'), 'off-shoulder': ('露肩', 'off-shoulder'),
    'ribbon-trimmed': ('丝带边', 'ribbon-trim'), 'gold-trimmed': ('金边', 'gold-trim'),
    'lace-up': ('系带', 'lace-up'), 'cross-laced': ('交叉系带', 'cross-laced'), 'print': ('印花', 'print'),
    'star-print': ('星形印花', 'star-pattern'), 'heart-print': ('爱心印花', 'heart-pattern'),
    'fur': ('毛绒', 'fur-trim'), 'suspender': ('背带', 'suspender'), 'rimless': ('无框', 'rimless'),
    'low': ('低位置', 'low'), 'high': ('高位置', 'high'), 'asymmetrical': ('不对称', 'asymmetrical'),
}


def primitives() -> dict[str, str]:
    shapes = {key: '' for key in ('hair','eyes','face','body','pose')}
    shapes['person'] = _person()
    shapes['people'] = _person(37,30,.65) + _person(91,30,.65) + A(48,74,80,74)
    shapes['couple'] = _person(33,30,.62) + _person(95,30,.62) + P('M64 66 c-28 -16 -16 -37 0 -21 c16 -16 28 5 0 21Z','{accent}')
    shapes['shirt'] = P('M42 24 L54 19 Q64 35 74 19 L86 24 L112 47 L97 65 L85 53 L88 113 L40 113 L43 53 L31 65 L16 47Z','{fill}') + P('M64 35 L64 110',width=1)
    shapes['tshirt'] = P('M43 25 L54 19 Q64 34 74 19 L85 25 L111 42 L98 60 L84 51 L86 111 L42 111 L44 51 L30 60 L17 42Z','{fill}')
    shapes['sleeveless'] = P('M43 19 L54 20 Q64 36 74 20 L85 19 L79 47 L86 112 L42 112 L49 47Z','{fill}')
    shapes['dress'] = P('M46 15 L56 18 L64 28 L72 18 L82 15 L89 43 L76 57 L108 114 Q64 123 20 114 L52 57 L39 43Z','{fill}')
    shapes['skirt'] = P('M44 28 L84 28 L111 104 Q64 118 17 104Z','{fill}') + P('M44 36 L84 36 M50 43 L41 102 M64 43 L64 107 M78 43 L87 102',width=2)
    shapes['pants'] = P('M35 16 L93 16 L98 114 L74 114 L64 61 L54 114 L30 114Z','{fill}') + P('M36 29 L92 29 M64 29 L64 52',width=2)
    shapes['shorts'] = P('M31 26 L97 26 L101 87 L73 87 L64 59 L55 87 L27 87Z','{fill}') + P('M32 38 L96 38',width=2)
    shapes['coat'] = P('M43 16 L55 15 L64 33 L73 15 L85 16 L106 39 L103 84 L88 84 L90 117 L38 117 L40 84 L25 84 L22 39Z','{fill}') + P('M54 21 L64 36 L49 50 M74 21 L64 36 L79 50 M64 36 L64 116',width=2)
    shapes['hoodie'] = shapes['shirt'] + P('M47 26 Q39 -5 64 5 Q89 -5 81 26 L74 38 L54 38Z','{fill}') + P('M48 86 L80 86 L84 100 L44 100Z',width=2)
    shapes['kimono'] = P('M42 15 L64 38 L86 15 L118 36 L112 88 L85 76 L94 116 L34 116 L43 76 L16 88 L10 36Z','{fill}') + P('M46 23 L78 68 M82 23 L50 68',width=2) + R(40,65,48,17,'{accent}')
    shapes['bodysuit'] = P('M43 18 L54 16 L64 29 L74 16 L85 18 L93 44 L80 61 L86 85 L76 112 L66 112 L64 91 L62 112 L52 112 L42 85 L48 61 L35 44Z','{fill}')
    shapes['leotard'] = P('M42 18 L53 16 L64 29 L75 16 L86 18 L78 52 L88 75 L64 103 L40 75 L50 52Z','{fill}')
    shapes['bikini'] = P('M33 31 Q48 10 60 48 L28 48Z M95 31 Q80 10 68 48 L100 48Z','{fill}') + P('M59 39 L69 39 M22 39 L29 39 M99 39 L106 39') + P('M27 79 L101 79 L64 113Z','{fill}')
    shapes['bra'] = P('M26 61 Q26 30 45 30 Q61 30 61 61Z M67 61 Q67 30 83 30 Q102 30 102 61Z','{fill}') + P('M61 48 L67 48 M28 41 L29 13 M100 41 L99 13',width=3)
    shapes['panties'] = P('M21 35 Q64 48 107 35 L98 62 L69 101 L59 101 L30 62Z','{fill}') + P('M24 44 Q64 56 104 44',width=2)
    shapes['socks'] = P('M42 12 L78 12 L78 79 Q99 90 102 105 Q89 121 47 111 L31 98 L42 74Z','{fill}') + P('M43 28 L76 28',width=2)
    shapes['pantyhose'] = shapes['pants'] + P('M29 105 L21 116 L52 118 M76 118 L107 116 L97 105','{fill}')
    shapes['boots'] = P('M41 12 L82 12 L80 83 L109 97 L109 113 L26 113 L24 99 L39 85Z','{fill}') + P('M40 29 L80 29 M28 104 L105 104',width=2)
    shapes['shoes'] = P('M28 56 L47 69 L57 56 L72 72 L110 91 L110 109 L19 109 L17 86Z','{fill}') + P('M22 99 L106 99 M53 73 L75 85 M59 69 L81 81',width=2)
    shapes['heels'] = P('M27 50 L46 72 L61 53 Q77 86 112 94 L111 108 L49 108 L30 81 L27 112 L18 112 L18 67Z','{fill}')
    shapes['sandals'] = P('M29 42 Q63 20 88 43 L105 100 Q68 121 21 104Z','{fill}') + P('M29 50 L86 50 M25 69 L94 69 M65 38 L64 100',stroke='{paper}',width=6)
    shapes['gloves'] = P('M37 111 L36 80 L23 56 Q21 46 30 48 L42 62 L40 27 Q43 14 49 27 L51 49 L52 17 Q56 6 61 18 L61 48 L64 19 Q71 9 73 23 L71 52 L76 35 Q84 26 87 40 L82 85 L78 112Z','{fill}')
    shapes['sleeves'] = P('M24 22 L52 28 L44 112 L15 105Z M104 22 L76 28 L84 112 L113 105Z','{fill}')
    shapes['cape'] = P('M51 14 Q64 24 77 14 L114 111 Q64 126 14 111Z','{fill}') + P('M54 27 L47 111 M74 27 L81 111',width=2)
    shapes['armor'] = P('M42 19 L56 21 L64 34 L72 21 L86 19 L108 38 L91 57 L81 50 L86 85 L75 113 L53 113 L42 85 L47 50 L37 57 L20 38Z','{fill}') + P('M48 52 L64 69 L80 52 M45 86 L83 86 M51 98 L77 98',width=3)
    shapes['apron'] = P('M48 17 L80 17 L79 60 L101 113 L27 113 L49 60Z','{fill}') + P('M48 23 L36 10 M80 23 L92 10 M43 63 L20 61 M85 63 L108 61',width=3) + R(51,70,26,23,'{accent}')
    shapes['hat'] = P('M33 77 L39 39 Q64 20 89 39 L95 77Z','{fill}') + P('M10 80 Q64 56 118 80 Q124 102 64 101 Q4 102 10 80Z','{fill}')
    shapes['cap'] = P('M24 75 Q22 28 63 28 Q103 28 105 75Z','{fill}') + P('M62 75 L121 84 Q109 98 65 92Z','{fill}')
    shapes['beret'] = P('M16 60 Q7 29 58 28 Q99 12 116 52 L103 77 L34 80Z','{fill}') + P('M35 72 L102 68 M65 29 L69 17',width=3)
    shapes['witch_hat'] = P('M28 81 L53 13 L85 26 L68 29 L100 81Z','{fill}') + P('M7 83 Q64 63 121 83 Q116 111 64 104 Q12 111 7 83Z','{fill}')
    shapes['helmet'] = P('M24 94 L24 49 Q26 13 64 12 Q103 13 104 49 L104 94 L85 96 L84 54 L44 54 L43 96Z','{fill}') + P('M48 61 L80 61 L77 93 L51 93Z','{accent}')
    shapes['hood'] = P('M21 105 Q12 18 64 13 Q116 18 107 105 L88 113 L78 88 Q102 40 64 35 Q26 40 50 88 L40 113Z','{fill}')
    shapes['tie'] = P('M49 14 L79 14 L70 35 L82 103 L64 120 L46 103 L58 35Z','{fill}')
    shapes['bow'] = P('M60 52 L20 26 L20 100 L60 76Z M68 52 L108 26 L108 100 L68 76Z','{fill}') + R(54,48,20,32,'{accent}')
    shapes['ribbon'] = shapes['bow'] + P('M58 76 L34 118 L50 109 L60 121 L65 79 M70 76 L94 118 L78 109 L68 121 L63 79','{fill}')
    shapes['belt'] = R(10,49,108,30) + R(51,42,33,44,'{accent}') + P('M67 47 L67 81',width=2)
    shapes['collar'] = P('M21 31 L64 55 L107 31 L100 80 L77 89 L64 67 L51 89 L28 80Z','{fill}')
    shapes['choker'] = R(15,51,98,26) + C(64,80,10,'{accent}')
    shapes['scarf'] = P('M25 25 L101 25 L99 56 L74 59 L85 112 L59 116 L48 62 L26 57Z','{fill}')
    shapes['glasses'] = C(31,63,25,'{paper}') + C(97,63,25,'{paper}') + P('M56 61 Q64 56 72 61 M6 57 L2 51 M122 57 L126 51',width=4)
    shapes['goggles'] = R(9,39,46,46) + R(73,39,46,46) + P('M55 59 L73 59 M9 48 L0 48 M119 48 L128 48',width=5)
    shapes['eyepatch'] = P('M37 32 L82 37 L82 79 Q61 98 39 77Z','{fill}') + P('M4 15 L37 38 M82 50 L124 88',width=4)
    shapes['mask'] = P('M22 42 Q64 28 106 42 L98 83 Q64 105 30 83Z','{fill}') + P('M25 49 Q3 49 14 75 L31 78 M103 49 Q125 49 114 75 L97 78 M39 53 L90 53 M37 65 L91 65 M39 77 L89 77',width=2)
    shapes['necklace'] = P('M20 24 Q18 95 64 101 Q110 95 108 24',stroke='{fill}',width=6) + S(64,104,15,'{accent}')
    shapes['earring'] = C(64,73,29,'{fill}') + C(64,73,17,'{paper}') + C(64,32,7,'{accent}')
    shapes['ring'] = C(64,76,32,'{fill}') + C(64,76,22,'{paper}') + P('M44 38 L52 16 L76 16 L84 38 L64 51Z','{accent}')
    shapes['bracelet'] = C(64,64,41,'{fill}') + C(64,64,28,'{paper}') + C(103,66,7,'{accent}')
    shapes['headband'] = P('M18 104 Q-3 7 64 10 Q131 7 110 104 L98 100 Q111 26 64 26 Q17 26 30 100Z','{fill}')
    shapes['hairclip'] = R(10,50,108,24) + P('M24 57 L104 57',width=2)
    shapes['crown'] = P('M22 91 L12 31 L40 54 L64 15 L88 54 L116 31 L106 91Z','{fill}') + R(22,91,84,20,'{accent}')
    shapes['halo'] = '<ellipse cx="64" cy="56" rx="51" ry="22" fill="none" stroke="{fill}" stroke-width="10"/>'
    shapes['ears'] = P('M24 88 L19 20 L60 70 M104 88 L109 20 L68 70','{fill}') + P('M31 61 L29 37 L47 67 M97 61 L99 37 L81 67','{accent}')
    shapes['rabbit_ears'] = P('M45 110 Q13 -8 32 9 Q51 16 58 96Z M83 110 Q115 -8 96 9 Q77 16 70 96Z','{fill}')
    shapes['horns'] = P('M24 105 Q37 47 16 15 Q54 37 54 91Z M104 105 Q91 47 112 15 Q74 37 74 91Z','{fill}')
    shapes['wings'] = P('M61 89 Q27 109 14 79 L32 82 L8 55 L28 62 L10 23 Q49 35 61 89Z M67 89 Q101 109 114 79 L96 82 L120 55 L100 62 L118 23 Q79 35 67 89Z','{fill}')
    shapes['bat_wings'] = P('M60 92 Q26 82 9 111 L18 54 L39 29 L62 62 M68 92 Q102 82 119 111 L110 54 L89 29 L66 62','{fill}')
    shapes['tail'] = P('M31 100 Q91 125 91 67 Q98 28 45 20 Q105 2 113 67 Q109 117 64 115Z','{fill}')
    shapes['flower'] = ''.join(f'<ellipse cx="64" cy="35" rx="15" ry="24" fill="{{fill}}" stroke="{{ink}}" stroke-width="2" transform="rotate({i*60} 64 64)"/>' for i in range(6)) + C(64,64,16,'{accent}')
    shapes['leaf'] = P('M22 106 Q5 14 106 18 Q119 106 22 106Z','{fill}') + P('M22 106 L91 34 M49 77 L42 46 M69 58 L96 64',width=2)
    shapes['tree'] = P('M54 74 L74 74 L81 117 L47 117Z','#b99168') + C(43,55,27,'{fill}') + C(83,55,27,'{fill}') + C(64,34,29,'{fill}')
    shapes['plant'] = P('M31 78 L97 78 L88 117 L40 117Z','{accent}') + P('M64 80 L64 36',stroke='{fill}',width=6) + P('M64 58 Q20 59 23 25 Q59 24 64 58Z M64 47 Q106 48 104 12 Q70 12 64 47Z','{fill}')
    shapes['heart'] = P('M64 111 Q-13 58 23 23 Q48 4 64 37 Q80 4 105 23 Q141 58 64 111Z','{fill}')
    shapes['star'] = S(64,64,52)
    shapes['sparkle'] = P('M64 9 L77 50 L117 64 L77 78 L64 119 L51 78 L11 64 L51 50Z','{fill}') + S(107,20,10,'{accent}')
    shapes['moon'] = P('M91 16 Q14 17 17 76 Q30 126 103 99 Q42 104 43 60 Q45 27 91 16Z','{fill}')
    shapes['sun'] = C(64,64,25) + ''.join(f'<path d="M64 7 L64 24" stroke="{{fill}}" stroke-width="6" transform="rotate({i*45} 64 64)"/>' for i in range(8))
    shapes['cloud'] = P('M25 88 Q2 83 12 62 Q14 49 33 48 Q42 16 67 34 Q88 20 100 50 Q125 52 119 74 Q118 90 100 88Z','{fill}')
    shapes['rain'] = shapes['cloud'] + P('M35 100 l-8 17 M65 100 l-8 17 M95 100 l-8 17',stroke='#6dabe6',width=4)
    shapes['snow'] = P('M64 10 L64 118 M17 37 L111 91 M17 91 L111 37 M51 20 L64 32 L77 20 M51 108 L64 96 L77 108',stroke='{fill}',width=5)
    shapes['fire'] = P('M64 9 Q111 55 102 93 Q79 133 38 110 Q7 89 34 44 Q36 76 51 66 Q74 54 64 9Z','{fill}') + P('M62 65 Q89 95 69 114 Q40 111 49 88Z','{accent}')
    shapes['water'] = P('M8 44 Q22 27 38 44 Q54 61 70 44 Q86 27 102 44 Q114 56 121 44 M8 72 Q22 55 38 72 Q54 89 70 72 Q86 55 102 72 Q114 84 121 72 M8 100 Q22 83 38 100 Q54 117 70 100 Q86 83 102 100 Q114 112 121 100',stroke='{fill}',width=5)
    shapes['drop'] = P('M64 10 Q13 66 28 97 Q64 132 100 97 Q115 66 64 10Z','{fill}')
    shapes['wind'] = P('M8 39 L86 39 Q117 39 107 19 Q94 8 84 23 M8 64 L111 64 M8 87 L73 87 Q108 90 94 109 Q77 120 68 104',stroke='{fill}',width=5)
    shapes['background'] = R(10,14,108,100) + _person(66,51,.52)
    shapes['frame'] = R(9,13,110,102,'{paper}') + _person(64,22,.82)
    shapes['portrait'] = R(12,9,104,111,'{paper}') + C(64,46,22) + P('M25 113 Q27 73 64 73 Q101 73 103 113Z','{fill}')
    shapes['closeup'] = R(8,8,112,112,'{paper}') + C(64,61,50) + P('M25 47 L48 47 M79 47 L102 47 M46 91 L82 91',width=4)
    shapes['upper_body'] = R(12,8,104,112,'{paper}') + _person(64,18,.94) + P('M14 88 L114 88',stroke='{accent}',width=5)
    shapes['angle_above'] = _person(64,48,.68) + R(13,10,30,21,'{accent}') + A(42,24,65,51)
    shapes['angle_below'] = _person(64,25,.68) + R(13,91,30,21,'{accent}') + A(43,95,66,67)
    shapes['angle_side'] = _person(75,25,.74) + R(9,50,30,21,'{accent}') + A(41,61,65,61)
    shapes['comic'] = R(9,9,51,48) + R(68,9,51,48) + R(9,65,110,54) + C(30,31,9,'{paper}') + C(91,31,9,'{paper}')
    shapes['speech'] = P('M13 22 L115 22 L115 84 L62 84 L31 112 L36 84 L13 84Z','{paper}') + P('M30 44 L99 44 M30 61 L81 61',width=4)
    shapes['text'] = R(10,15,108,97,'{paper}') + T('Aa',64,79,43) + P('M24 97 L104 97',width=2)
    shapes['signature'] = P('M12 95 Q39 41 59 21 Q80 6 50 73 Q70 43 73 59 Q77 80 94 59 Q113 47 111 76',stroke='{fill}',width=5) + P('M9 109 L116 109',width=2)
    shapes['censor'] = shapes['portrait'] + R(13,49,103,27,'{ink}')
    shapes['mosaic'] = shapes['portrait'] + ''.join(R(x,y,15,15,'{accent}' if (x+y)%30 else '{fill}',0) for x in range(26,102,15) for y in range(39,84,15))
    shapes['light'] = _person(75,32,.73) + S(21,22,15,'{accent}') + A(35,34,58,52) + A(24,41,48,67)
    shapes['backlight'] = C(64,60,50,'{accent}') + _person(64,25,.78)
    shapes['blurry'] = R(11,11,106,106,'{paper}') + '<g opacity=".28">' + C(56,59,24) + C(71,59,24) + '</g>' + C(64,59,24,'{fill}')
    shapes['palette'] = P('M64 10 Q8 12 10 71 Q10 118 61 117 Q90 119 72 90 Q72 79 88 77 Q128 85 116 45 Q107 10 64 10Z','{paper}') + ''.join(C(x,y,8,col,'none') for x,y,col in ((36,36,'#dd646a'),(64,26,'#f1ce61'),(92,39,'#6aa780'),(96,65,'#579bd4'),(35,71,'#a48bcf')))
    shapes['pen'] = P('M27 103 L38 76 L91 18 L110 35 L55 94Z','{fill}') + P('M27 103 L47 96 L35 84Z','{ink}')
    shapes['camera'] = R(10,35,108,66) + R(35,24,38,15,'{accent}') + C(65,66,23,'{paper}') + C(65,66,14,'{fill}')
    shapes['play'] = R(10,22,108,85,'{paper}') + P('M50 40 L88 65 L50 90Z','{fill}')
    shapes['badge'] = R(17,18,94,92) + S(64,64,33,'{accent}')
    shapes['rating'] = R(17,18,94,92) + T('R',64,84,55)
    shapes['cat'] = P('M28 43 L19 12 L50 31 Q64 23 78 31 L109 12 L100 43 Q116 85 64 109 Q12 85 28 43Z','{fill}') + C(44,58,4,'{ink}') + C(84,58,4,'{ink}') + P('M58 75 L70 75 L64 83Z','{accent}') + P('M18 75 L47 79 M110 75 L81 79 M19 89 L47 86 M109 89 L81 86',width=2)
    shapes['dog'] = P('M33 29 Q15 27 9 49 L17 92 L35 73 Q64 123 93 73 L111 92 L119 49 Q113 27 95 29 Q64 15 33 29Z','{fill}') + C(45,56,4,'{ink}') + C(83,56,4,'{ink}') + C(64,76,8,'{accent}')
    shapes['rabbit'] = P('M40 53 Q10 5 31 7 Q45 8 53 45 M88 53 Q118 5 97 7 Q83 8 75 45','{fill}') + C(64,77,36) + C(48,70,4,'{ink}') + C(80,70,4,'{ink}') + C(64,85,5,'{accent}')
    shapes['horse'] = P('M34 34 L35 9 L55 25 L80 9 L91 34 L91 88 Q66 121 35 98 L25 76 L38 61Z','{fill}') + C(63,47,4,'{ink}') + P('M32 89 L60 87 M33 26 L26 55',width=3)
    shapes['bird'] = P('M21 86 Q15 41 66 42 Q82 12 99 29 Q110 35 105 45 L122 53 L102 64 Q90 109 47 105Z','{fill}') + P('M36 62 Q50 99 78 67',width=3) + C(91,37,3,'{ink}')
    shapes['butterfly'] = P('M60 61 Q18 7 10 32 Q0 62 47 72 Q9 76 29 113 Q49 124 60 78 M68 61 Q110 7 118 32 Q128 62 81 72 Q119 76 99 113 Q79 124 68 78','{fill}') + P('M64 39 L64 97 M62 43 L51 27 M66 43 L77 27',width=4)
    shapes['fish'] = P('M20 65 Q65 9 103 65 Q65 121 20 65Z','{fill}') + P('M22 65 L5 41 L5 89Z','{accent}') + C(86,57,4,'{ink}')
    shapes['bug'] = C(64,70,34) + C(64,28,18,'{accent}') + P('M64 38 L64 103 M32 53 L9 39 M30 72 L7 74 M33 92 L12 113 M96 53 L119 39 M98 72 L121 74 M95 92 L116 113',width=4)
    shapes['robot'] = R(25,21,78,55) + R(35,81,58,31) + C(45,45,7,'{accent}') + C(83,45,7,'{accent}') + P('M45 63 L83 63 M64 21 L64 9 M35 91 L12 104 M93 91 L116 104 M47 112 L42 122 M81 112 L86 122',width=4)
    shapes['book'] = P('M12 24 Q37 13 64 30 Q91 13 116 24 L116 109 Q90 98 64 115 Q38 98 12 109Z','{fill}') + P('M64 30 L64 115 M23 41 L49 43 M78 43 L104 41 M23 58 L49 60 M78 60 L104 58',width=2)
    shapes['phone'] = R(33,7,62,114) + R(40,20,48,80,'{paper}') + C(64,110,3,'{ink}')
    shapes['headphones'] = P('M17 80 L17 58 Q13 10 64 9 Q115 10 111 58 L111 80',stroke='{fill}',width=10) + R(10,53,24,54,'{fill}') + R(94,53,24,54,'{fill}')
    shapes['bag'] = R(22,39,84,78) + P('M42 39 L42 22 Q64 1 86 22 L86 39',stroke='{fill}',width=7)
    shapes['backpack'] = R(26,22,76,97) + R(36,67,56,42,'{accent}') + P('M48 22 L48 10 L80 10 L80 22 M26 51 L12 44 L12 99 L26 96 M102 51 L116 44 L116 99 L102 96',width=3)
    shapes['umbrella'] = P('M8 64 Q64 -12 120 64 Q105 54 91 66 Q78 53 64 67 Q50 53 36 66 Q22 54 8 64Z','{fill}') + P('M64 9 L64 110 Q62 123 49 112',width=4)
    shapes['cup'] = P('M25 26 L89 26 L83 105 L31 105Z','{fill}') + P('M89 37 Q124 32 111 66 L86 75',width=5)
    shapes['bottle'] = R(48,9,32,21,'{accent}') + P('M48 30 L48 42 L34 58 L34 116 L94 116 L94 58 L80 42 L80 30Z','{fill}') + R(36,70,56,25,'{paper}')
    shapes['plate'] = '<ellipse cx="64" cy="66" rx="54" ry="43" fill="{fill}" stroke="{ink}" stroke-width="3"/>' + '<ellipse cx="64" cy="66" rx="39" ry="29" fill="{paper}" stroke="{ink}" stroke-width="2"/>'
    shapes['fruit'] = P('M64 35 Q15 12 17 65 Q13 116 50 117 L64 111 L78 117 Q115 116 111 65 Q113 12 64 35Z','{fill}') + P('M64 37 Q58 12 77 10 M69 19 Q91 3 106 20 Q87 35 69 19Z','{accent}')
    shapes['cake'] = R(15,54,98,58) + P('M15 56 Q23 73 31 56 Q39 74 47 56 Q55 74 63 56 Q71 74 79 56 Q87 74 95 56 Q104 73 113 56','{accent}') + P('M64 52 L64 27',stroke='{fill}',width=6) + P('M64 9 Q46 26 64 30 Q82 26 64 9Z','#e89954')
    shapes['candy'] = C(64,63,27) + P('M37 49 L10 33 L10 93 L37 77 M91 49 L118 33 L118 93 L91 77','{accent}')
    shapes['sword'] = P('M72 5 L95 10 L55 89 L41 80Z','{fill}') + P('M30 75 L67 95 M45 85 L31 112',stroke='{accent}',width=8)
    shapes['knife'] = P('M78 14 Q113 45 65 83 L51 75Z','{fill}') + P('M57 81 L31 115',stroke='{accent}',width=12)
    shapes['gun'] = P('M13 36 L115 36 L115 57 L72 57 L56 106 L32 99 L40 59 L13 59Z','{fill}') + P('M70 58 L87 58 L83 74 L65 74',width=3)
    shapes['rifle'] = P('M8 43 L97 43 L97 53 L119 53 L119 62 L88 62 L79 76 L54 76 L46 104 L32 100 L38 71 L8 85Z','{fill}') + R(65,23,20,16,'{accent}')
    shapes['staff'] = P('M63 35 L50 122',stroke='{fill}',width=9) + C(68,21,17,'{accent}') + S(68,21,11,'{paper}')
    shapes['weapon'] = shapes['sword']
    shapes['weapons'] = f'<g transform="translate(5 0) scale(.7)">{shapes["sword"]}</g><g transform="translate(35 40) scale(.7)">{shapes["gun"]}</g>'
    shapes['chain'] = ''.join(f'<ellipse cx="{30+i*22}" cy="{92-i*19}" rx="20" ry="11" transform="rotate(-40 {30+i*22} {92-i*19})" fill="none" stroke="{{fill}}" stroke-width="5"/>' for i in range(4))
    shapes['rope'] = P('M12 99 Q115 128 102 49 Q91 1 57 24 Q21 42 64 67 Q115 101 115 22',stroke='{fill}',width=8)
    shapes['gem'] = P('M29 21 L99 21 L119 48 L64 118 L9 48Z','{fill}') + P('M9 48 L119 48 M29 21 L42 48 L64 118 L86 48 L99 21 M42 48 L64 21 L86 48',width=2)
    shapes['feather'] = P('M24 109 Q2 33 97 9 Q123 58 24 109Z','{fill}') + P('M20 118 L90 20 M34 82 L23 59 M50 65 L91 62 M61 49 L48 29',width=2)
    shapes['bell'] = P('M27 90 Q41 82 39 54 Q40 25 64 24 Q88 25 89 54 Q87 82 101 90Z','{fill}') + C(64,20,7,'{accent}') + C(64,98,11,'{accent}')
    shapes['microphone'] = P('M44 23 Q64 1 84 23 L84 65 Q64 87 44 65Z','{fill}') + P('M33 48 Q24 95 64 95 Q104 95 95 48 M64 95 L64 120 M42 120 L86 120',width=4)
    shapes['music'] = P('M45 90 L45 28 L99 16 L99 79',stroke='{fill}',width=7) + '<ellipse cx="31" cy="97" rx="17" ry="12" fill="{fill}"/>' + '<ellipse cx="85" cy="86" rx="17" ry="12" fill="{fill}"/>'
    shapes['ball'] = C(64,64,49) + P('M17 64 L111 64 M64 16 Q31 65 64 113 M64 16 Q97 65 64 113',width=3)
    shapes['box'] = P('M13 31 L64 10 L115 31 L115 97 L64 118 L13 97Z','{fill}') + P('M13 31 L64 52 L115 31 M64 52 L64 118',width=3)
    shapes['gift'] = R(19,41,90,73) + R(12,33,104,22) + P('M64 35 Q18 -5 23 20 Q28 39 64 35 Q110 -5 105 20 Q100 39 64 35 M64 35 L64 114',stroke='{accent}',width=7)
    shapes['pillow'] = P('M14 26 Q64 39 114 26 Q98 64 114 102 Q64 88 14 102 Q30 64 14 26Z','{fill}')
    shapes['chair'] = R(33,12,60,48) + R(27,68,72,19,'{accent}') + P('M33 60 L33 112 M93 60 L93 112',width=6)
    shapes['bed'] = R(12,63,104,33) + R(17,48,40,20,'{paper}') + P('M12 40 L12 115 M116 63 L116 115',width=6)
    shapes['table'] = R(7,36,114,24) + P('M19 60 L19 117 M109 60 L109 117',width=7)
    shapes['window'] = R(13,9,102,108,'{paper}') + R(23,19,82,88,'{fill}') + P('M64 19 L64 107 M23 63 L105 63',stroke='{paper}',width=7)
    shapes['building'] = R(30,12,68,107) + ''.join(R(x,y,15,17,'{paper}',0) for x in (40,73) for y in (24,55,86))
    shapes['indoors'] = P('M9 118 L9 17 L119 17 L119 118 M9 17 L35 38 L94 38 L119 17 M35 38 L35 93 L9 118 M94 38 L94 93 L119 118 M35 93 L94 93',stroke='{fill}',width=4) + R(51,48,28,30,'{accent}')
    shapes['outdoors'] = shapes['sun'][:0] + C(100,25,17,'{accent}') + P('M3 106 L37 42 L69 91 L90 60 L125 106Z','{fill}') + P('M3 112 L125 112',width=3)
    shapes['beach'] = C(99,23,17,'{accent}') + P('M8 77 Q42 40 68 61 Q99 93 119 71',stroke='#68c7ca',width=7) + P('M8 114 Q70 67 120 104Z','{fill}')
    shapes['car'] = P('M10 83 L17 54 L34 50 L45 26 L84 26 L100 52 L115 60 L117 93 L10 93Z','{fill}') + C(33,96,14,'{ink}') + C(96,96,14,'{ink}') + P('M47 32 L83 32 L95 52 L36 52Z','{paper}')
    shapes['animals'] = f'<g transform="translate(3 30) scale(.6)">{shapes["dog"]}</g><g transform="translate(63 4) scale(.48)">{shapes["bird"]}</g><g transform="translate(65 66) scale(.43)">{shapes["cat"]}</g>'
    shapes['motor_vehicle'] = shapes['car'] + C(102,27,17,'{accent}') + P('M102 5 L102 13 M102 41 L102 49 M80 27 L88 27 M116 27 L124 27',width=5)
    shapes['virtual_streamer'] = R(6,16,116,88,'{paper}') + C(57,45,17) + P('M31 87 Q33 64 57 64 Q81 64 83 87Z','{fill}') + P('M93 33 L113 45 L93 57Z','{accent}') + P('M64 105 L64 117 M43 117 L85 117',width=4)
    shapes['hand'] = shapes['gloves']
    shapes['foot'] = shapes['socks']
    shapes['nails'] = shapes['hand'] + R(39,26,10,17,'{accent}') + R(52,15,10,17,'{accent}') + R(64,23,10,17,'{accent}')
    # Distinct long-tail subjects. These are original vector drawings, not
    # downloaded thumbnails or text badges posing as semantic illustrations.
    shapes['tray'] = P('M9 63 L119 63 L110 87 L18 87Z','{fill}') + P('M19 72 L109 72',width=2)
    shapes['pouch'] = P('M39 18 L89 18 L83 42 Q113 53 109 94 Q91 123 37 111 Q15 85 26 61 L45 42Z','{fill}') + P('M39 30 L89 30 M44 39 L19 41 M84 39 L107 43',stroke='{accent}',width=4)
    shapes['headset'] = shapes['headphones'] + P('M105 96 L96 118 L65 118',stroke='{accent}',width=4) + R(55,111,20,13,'{fill}')
    shapes['top_hat'] = R(35,12,58,79) + P('M9 95 Q64 76 119 95 Q112 115 64 114 Q16 115 9 95Z','{fill}') + R(36,70,56,18,'{accent}',0)
    shapes['santa_hat'] = P('M19 89 Q37 18 92 20 Q100 33 108 68 L91 78 Q93 40 81 42 L80 89Z','{fill}') + R(15,86,73,26,'{paper}') + C(107,77,13,'{paper}')
    shapes['sun_hat'] = P('M32 77 L42 27 Q64 15 86 27 L96 77 Q128 85 120 102 Q64 124 8 102 Q0 85 32 77Z','{fill}') + P('M31 76 Q64 88 97 76',stroke='{accent}',width=6)
    shapes['beanie'] = P('M19 83 Q17 12 64 13 Q111 12 109 83Z','{fill}') + R(17,81,94,27,'{accent}') + P('M37 40 L33 77 M64 32 L64 77 M91 40 L95 77',width=2)
    shapes['vest'] = P('M43 14 L53 16 L64 54 L75 16 L85 14 L82 40 L96 69 L86 113 L64 104 L42 113 L32 69 L46 40Z','{fill}') + P('M64 54 L64 105',width=2)
    shapes['watch'] = R(48,5,32,32) + R(48,91,32,32) + C(64,64,34,'{paper}') + P('M64 42 L64 64 L83 71',width=4)
    shapes['pendant'] = P('M20 10 Q24 74 64 86 Q104 74 108 10',stroke='{fill}',width=5) + P('M64 79 L82 102 L64 122 L46 102Z','{accent}')
    shapes['cuff'] = P('M22 39 L102 31 L107 88 L27 97Z','{fill}') + P('M43 38 L48 93',stroke='{accent}',width=4) + C(78,77,5,'{accent}')
    shapes['piano'] = R(8,30,112,70,'{fill}') + R(12,65,104,32,'{paper}') + P('M26 65 L26 95 M42 65 L42 95 M58 65 L58 95 M74 65 L74 95 M90 65 L90 95 M106 65 L106 95',width=2) + ''.join(R(x,65,8,19,'{ink}',0) for x in (21,37,69,85,101))
    shapes['guitar'] = P('M57 61 L81 10 L92 16 L68 68 Q97 87 80 107 Q49 132 22 99 Q4 76 33 62 Q36 40 57 61Z','{fill}') + C(48,83,10,'{paper}') + P('M48 83 L86 19 M30 95 L49 105',width=3)
    shapes['violin'] = P('M60 50 L71 9 L82 12 L72 55 Q92 48 94 65 Q83 72 91 84 Q107 103 82 115 Q46 129 32 104 Q39 88 38 75 Q23 62 35 53 Q46 42 60 50Z','{fill}') + P('M56 100 L75 25 M20 112 L111 13',stroke='{accent}',width=4)
    shapes['trumpet'] = P('M14 56 L79 56 L111 29 L111 101 L79 78 L14 78Z','{fill}') + P('M33 53 L33 36 M48 53 L48 36 M63 53 L63 36 M27 84 Q28 112 62 110 L76 81',width=5)
    shapes['instrument'] = f'<g transform="translate(0 0) scale(.78)">{shapes["guitar"]}</g><g transform="translate(58 68) scale(.48)">{shapes["piano"]}</g>'
    shapes['lantern'] = P('M39 24 Q34 3 64 5 Q94 3 89 24 M36 35 L25 104 L103 104 L92 35Z','{fill}') + R(37,41,54,52,'{paper}') + P('M64 52 Q41 81 64 88 Q87 81 64 52Z','#e89954')
    shapes['lamp'] = P('M36 19 L92 19 L112 62 L16 62Z','{fill}') + P('M64 63 L64 109 M39 115 L89 115',width=7)
    shapes['cigarette'] = P('M16 88 L105 58 L111 72 L22 102Z','{paper}') + P('M16 88 L37 81 L43 95 L22 102Z','{accent}') + P('M102 43 Q85 32 106 21 Q120 9 102 5',stroke='{fill}',width=3)
    shapes['swim_ring'] = '<ellipse cx="64" cy="65" rx="55" ry="39" fill="{fill}" stroke="{ink}" stroke-width="3"/><ellipse cx="64" cy="65" rx="29" ry="17" fill="{paper}" stroke="{ink}" stroke-width="3"/>'
    shapes['bowl'] = P('M11 53 Q64 77 117 53 Q107 116 64 115 Q21 116 11 53Z','{fill}') + '<ellipse cx="64" cy="52" rx="53" ry="16" fill="{paper}" stroke="{ink}" stroke-width="3"/>'
    shapes['spoon'] = P('M67 60 L49 117',stroke='{fill}',width=9) + '<ellipse cx="76" cy="36" rx="22" ry="32" transform="rotate(20 76 36)" fill="{fill}" stroke="{ink}" stroke-width="3"/>'
    shapes['fork'] = P('M51 117 L67 63 L78 63 L91 19 M67 62 L62 47 L70 11 M75 45 L83 14',stroke='{fill}',width=6)
    shapes['chopsticks'] = P('M43 118 L66 11 M58 118 L90 15',stroke='{fill}',width=7)
    shapes['lollipop'] = C(68,45,34) + P('M56 76 L40 122',stroke='{accent}',width=7) + P('M47 37 Q54 16 77 30 Q93 43 71 60 Q54 68 55 43 Q59 33 69 40',width=3)
    shapes['popsicle'] = P('M34 26 Q64 -9 94 26 L94 85 L34 85Z','{fill}') + R(56,87,16,35,'{accent}')
    shapes['ice_cream'] = P('M36 63 L92 63 L64 121Z','{accent}') + C(64,39,31,'{fill}') + P('M44 72 L77 101 M40 89 L78 75',width=2)
    shapes['strawberry'] = P('M23 41 Q-1 17 49 22 L64 32 L79 22 Q129 17 105 41 Q105 87 64 119 Q23 87 23 41Z','{fill}') + P('M22 31 L53 34 L42 9 L64 25 L82 9 L75 34 L106 31 L89 48 L39 48Z','{accent}') + ''.join(C(x,y,2,'{paper}','none') for x,y in ((40,59),(65,61),(88,59),(52,82),(79,82),(65,100)))
    shapes['chocolate'] = R(20,16,88,103,'{fill}') + ''.join(R(x,y,23,25,'{accent}',0) for x in (27,53,79) for y in (25,53,81))
    shapes['banana'] = P('M99 14 Q112 113 37 117 Q5 118 12 94 Q95 111 87 12Z','{fill}') + P('M29 104 Q88 106 99 37',width=2)
    shapes['bread'] = P('M24 51 Q1 43 12 25 Q15 11 64 11 Q113 11 116 25 Q127 43 104 51 L104 115 L24 115Z','{fill}') + P('M34 64 L94 64',width=2)
    shapes['pizza'] = P('M13 36 Q64 2 115 36 L64 122Z','{fill}') + P('M13 36 Q64 2 115 36',stroke='{accent}',width=10) + C(48,54,8,'{accent}') + C(78,54,8,'{accent}') + C(64,88,7,'{accent}')
    shapes['burger'] = P('M15 48 Q18 6 64 8 Q110 6 113 48Z','{fill}') + R(10,55,108,17,'{accent}') + P('M12 74 L36 85 L57 76 L83 85 L116 74',stroke='#6aa780',width=7) + P('M14 88 L114 88 Q108 118 64 118 Q20 118 14 88Z','{fill}')
    shapes['egg'] = P('M64 8 Q9 53 31 99 Q64 130 97 99 Q119 53 64 8Z','{paper}')
    shapes['meat'] = P('M31 38 Q27 11 66 15 Q113 31 114 71 Q112 102 69 104 Q24 118 19 75Z','{fill}') + C(70,58,15,'{paper}')
    shapes['rice'] = shapes['bowl'] + P('M22 51 Q27 23 49 28 Q66 6 86 30 Q107 29 108 51Z','{paper}')
    shapes['knife_fork'] = f'<g transform="translate(-4 0) scale(.7)">{shapes["fork"]}</g><g transform="translate(43 18) scale(.7)">{shapes["knife"]}</g>'
    shapes['can'] = R(29,17,70,99,'{fill}') + '<ellipse cx="64" cy="17" rx="35" ry="9" fill="{paper}" stroke="{ink}" stroke-width="3"/>' + R(31,51,66,27,'{accent}')
    shapes['balloon'] = '<ellipse cx="64" cy="43" rx="37" ry="39" fill="{fill}" stroke="{ink}" stroke-width="3"/>' + P('M64 82 L58 89 L70 89Z','{accent}') + P('M64 89 Q40 106 63 124',width=2)
    shapes['card'] = R(22,6,84,116,'{paper}') + T('A',39,35,22) + S(65,67,24,'{fill}')
    shapes['shield'] = P('M19 17 L64 10 L109 17 L102 75 Q95 104 64 123 Q33 104 26 75Z','{fill}') + P('M64 20 L64 110 M31 44 L97 44',stroke='{accent}',width=6)
    shapes['spear'] = P('M26 117 L79 40',stroke='{accent}',width=8) + P('M82 4 L103 35 L72 62 L68 25Z','{fill}')
    shapes['bow_weapon'] = P('M87 9 Q16 64 87 119',stroke='{fill}',width=7) + P('M87 9 L87 119 M18 64 L117 64 M103 53 L118 64 L103 75',width=3)
    shapes['broom'] = P('M92 7 L56 76',stroke='{accent}',width=8) + P('M53 70 L80 84 L65 119 L12 97Z','{fill}') + P('M37 85 L23 103 M48 89 L38 111 M62 95 L52 116',width=2)
    shapes['hammer'] = P('M49 114 L68 44',stroke='{accent}',width=11) + P('M20 27 L98 47 L110 27 L39 8Z','{fill}')
    shapes['key'] = C(43,35,25,'none') + P('M58 54 L109 104 L116 98 M87 82 L97 72',stroke='{fill}',width=8)
    shapes['scissors'] = C(31,88,18,'none') + C(83,99,18,'none') + P('M41 74 L94 8 M75 84 L37 12',stroke='{fill}',width=6) + C(59,52,4,'{accent}')
    shapes['pencil'] = P('M22 103 L34 76 L91 14 L110 32 L52 94Z','{fill}') + P('M22 103 L43 96 L31 84Z','{paper}') + P('M86 22 L101 36',stroke='{accent}',width=7)
    shapes['scroll'] = P('M19 26 L93 26 L93 105 L22 105 Q42 113 41 92 L41 38 Q41 10 19 26Z','{fill}') + P('M41 105 L103 105 Q121 105 108 88 L94 88 M21 26 L15 33 M52 45 L83 45 M52 60 L81 60 M52 76 L83 76',width=3)
    shapes['door'] = R(24,9,80,112,'{fill}') + R(34,20,60,90,'{paper}') + C(82,70,4,'{accent}')
    shapes['floor'] = P('M8 81 L43 44 L90 44 L121 81 L121 114 L8 114Z','{fill}') + P('M8 81 L121 81 M34 81 L44 114 M64 81 L64 114 M94 81 L84 114 M9 98 L120 98',width=2)
    shapes['stairs'] = P('M8 119 L8 98 L33 98 L33 74 L58 74 L58 50 L83 50 L83 26 L110 26 L110 119Z','{fill}')
    shapes['fence'] = ''.join(P(f'M{x} 113 L{x} 23 L{x+7} 12 L{x+14} 23 L{x+14} 113Z','{fill}') for x in (14,41,68,95)) + P('M9 51 L119 51 M9 85 L119 85',stroke='{accent}',width=6)
    shapes['railing'] = P('M8 34 L120 34 M12 39 L12 115 M39 39 L39 115 M65 39 L65 115 M91 39 L91 115 M117 39 L117 115',stroke='{fill}',width=6)
    shapes['couch'] = R(20,33,88,58) + R(8,56,20,48,'{accent}') + R(100,56,20,48,'{accent}') + R(28,70,72,31,'{fill}') + P('M21 105 L21 119 M107 105 L107 119',width=6)
    shapes['bookshelf'] = R(14,9,100,111,'{fill}') + ''.join(R(x,y,13,33,'{accent}') for x in (24,42,62,85) for y in (20,68)) + P('M18 58 L111 58 M18 108 L111 108',width=4)
    shapes['rock'] = P('M11 99 L29 43 L54 18 L94 38 L117 91 L93 114 L32 114Z','{fill}') + P('M29 43 L65 52 L93 114 M65 52 L94 38',width=2)
    shapes['mountain'] = P('M4 111 L50 18 L83 80 L105 47 L124 111Z','{fill}') + P('M31 58 L50 18 L69 56 L54 48 L45 57Z','{paper}')
    shapes['castle'] = R(10,38,28,77) + R(44,57,40,58) + R(90,38,28,77) + P('M7 38 L24 7 L41 38Z M87 38 L104 7 L121 38Z','{accent}') + P('M53 114 L53 82 Q64 67 75 82 L75 114Z','{paper}')
    shapes['bridge'] = P('M6 60 Q64 6 122 60 L122 89 Q64 54 6 89Z','{fill}') + P('M20 60 L20 30 M43 44 L43 13 M85 44 L85 13 M108 60 L108 30 M9 111 Q22 98 35 111 Q48 124 61 111 Q74 98 87 111 Q100 124 117 111',stroke='{accent}',width=4)
    shapes['palm'] = P('M65 116 Q79 68 63 43',stroke='{fill}',width=11) + P('M63 43 Q12 26 9 65 Q30 42 63 43 Q18 -3 20 17 Q27 39 63 43 Q72 -6 93 14 Q73 23 63 43 Q127 15 120 44 Q87 41 63 43',stroke='{accent}',width=8)
    shapes['snake'] = P('M15 111 Q111 133 111 83 Q111 46 48 72 Q5 88 17 43 Q22 22 62 21',stroke='{fill}',width=17) + P('M61 11 Q110 7 94 36 L62 33Z','{fill}') + C(83,18,3,'{ink}') + P('M98 26 L119 27 l-5 -5 M113 27 l-4 5',stroke='{accent}',width=2)
    shapes['skull'] = P('M35 89 Q-2 41 34 16 Q64 -3 94 16 Q130 41 93 89 L86 115 L42 115Z','{paper}') + C(43,58,15,'{ink}') + C(85,58,15,'{ink}') + P('M64 71 L55 86 L73 86Z','{ink}') + P('M51 98 L51 115 M64 98 L64 115 M77 98 L77 115',width=2)
    shapes['ghost'] = P('M19 116 L19 53 Q16 10 64 10 Q112 10 109 53 L109 116 L91 105 L73 119 L55 105 L37 119Z','{paper}') + C(45,49,7,'{ink}') + C(83,49,7,'{ink}') + C(64,78,10,'{ink}')
    shapes['bear'] = C(30,25,18) + C(98,25,18) + C(64,67,47) + C(43,57,4,'{ink}') + C(85,57,4,'{ink}') + C(64,83,20,'{paper}') + C(64,79,6,'{ink}')
    shapes['fox'] = P('M28 48 L13 6 L52 34 L76 34 L115 6 L100 48 Q104 89 64 117 Q24 89 28 48Z','{fill}') + P('M32 68 L64 109 L96 68 L84 87 L64 78 L44 87Z','{paper}') + C(43,57,4,'{ink}') + C(85,57,4,'{ink}') + C(64,92,5,'{ink}')
    shapes['frog'] = C(34,31,22) + C(94,31,22) + P('M14 57 Q64 28 114 57 Q133 100 64 118 Q-5 100 14 57Z','{fill}') + C(34,29,8,'{paper}') + C(94,29,8,'{paper}') + C(34,29,4,'{ink}') + C(94,29,4,'{ink}') + P('M36 84 Q64 103 92 84',width=3)
    shapes['turtle'] = C(64,65,35) + C(64,14,12,'{accent}') + C(19,65,11,'{accent}') + C(109,65,11,'{accent}') + C(38,109,10,'{accent}') + C(90,109,10,'{accent}') + P('M47 42 L81 42 L88 69 L64 89 L40 69Z',width=3)
    shapes['octopus'] = P('M34 54 Q22 6 64 9 Q106 6 94 54 Q119 33 117 74 Q125 110 111 115 Q105 118 105 79 Q94 44 92 114 M36 114 Q34 44 23 79 Q23 118 17 115 Q3 110 11 74 Q9 33 34 54Z','{fill}') + P('M45 65 Q54 89 45 119 M58 68 L58 122 M70 68 L70 122 M83 65 Q74 89 83 119',stroke='{fill}',width=7) + C(48,36,4,'{ink}') + C(80,36,4,'{ink}')
    shapes['dragon'] = shapes['fox'] + P('M22 31 L24 8 L40 29 M106 31 L104 8 L88 29','{accent}') + P('M45 81 L50 94 L55 81 M72 81 L77 94 L82 81','{paper}')
    shapes['paw'] = C(64,84,27) + C(24,49,14) + C(49,25,14) + C(80,25,14) + C(106,49,14)
    shapes['antlers'] = P('M46 117 L42 51 L17 24 M41 66 L10 65 M42 48 L44 12 M82 117 L86 51 L111 24 M87 66 L118 65 M86 48 L84 12',stroke='{fill}',width=8)
    shapes['fish_tail'] = P('M46 8 L82 8 Q103 49 73 85 Q113 64 121 91 Q92 116 64 101 Q36 116 7 91 Q15 64 55 85 Q25 49 46 8Z','{fill}') + P('M47 25 L80 25 M49 43 L77 43',width=2)
    shapes['feather_wing'] = shapes['wings'] + P('M20 32 L41 67 M16 57 L38 85 M26 81 L43 95 M108 32 L87 67 M112 57 L90 85 M102 81 L85 95',width=2)
    shapes['train'] = R(26,9,76,94) + R(33,19,62,37,'{paper}') + C(44,76,7,'{accent}') + C(84,76,7,'{accent}') + P('M41 105 L27 123 M87 105 L101 123 M64 20 L64 54',width=4)
    shapes['boat'] = P('M8 84 L120 84 L99 116 L29 116Z','{fill}') + P('M64 11 L64 82 M57 20 L57 75 L12 75Z M72 20 L111 75 L72 75Z','{paper}')
    shapes['plane'] = P('M59 8 L70 8 L76 56 L120 79 L120 92 L76 76 L75 103 L91 114 L90 123 L64 115 L38 123 L37 114 L53 103 L52 76 L8 92 L8 79 L52 56Z','{fill}')
    shapes['bicycle'] = C(29,92,23,'none') + C(99,92,23,'none') + P('M29 92 L53 49 L76 92 L29 92 M53 49 L83 49 L99 92 M76 92 L90 32 L78 28 M44 39 L63 39',stroke='{fill}',width=5)
    shapes['motorcycle'] = shapes['bicycle'] + P('M41 66 L67 55 L85 65 L73 91 L50 84Z','{fill}') + P('M40 53 L63 53',stroke='{accent}',width=8)
    shapes['computer'] = R(8,14,112,76,'{fill}') + R(16,22,96,59,'{paper}') + P('M64 91 L64 107 M35 112 L93 112',width=6)
    shapes['laptop'] = R(19,12,90,75,'{fill}') + R(26,19,76,61,'{paper}') + P('M19 89 L3 116 L125 116 L109 89Z','{fill}') + P('M38 102 L90 102',width=3)
    shapes['gamepad'] = P('M37 31 Q64 39 91 31 Q113 33 119 88 Q110 119 89 95 L76 77 L52 77 L39 95 Q18 119 9 88 Q15 33 37 31Z','{fill}') + P('M29 53 L29 78 M17 65 L41 65',width=5) + C(92,53,5,'{accent}') + C(106,66,5,'{accent}')
    shapes['cable'] = P('M15 118 Q117 119 101 67 Q94 44 42 69 Q-2 85 19 38 L48 14',stroke='{fill}',width=7) + R(42,3,28,24,'{accent}')
    shapes['lens_flare'] = S(28,29,24,'{accent}') + C(56,55,13,'none') + C(82,81,17,'none') + C(109,108,11,'{fill}')
    shapes['lightning'] = P('M78 5 L26 70 L57 65 L43 123 L106 43 L75 51Z','{fill}')
    shapes['bubble'] = C(63,64,47,'none') + P('M29 51 Q36 30 58 26',stroke='{fill}',width=5) + C(43,35,3,'{accent}','none')
    shapes['ice'] = P('M17 40 L67 18 L112 45 L112 95 L60 119 L17 92Z','{fill}') + P('M17 40 L60 65 L112 45 M60 65 L60 119',stroke='{paper}',width=4)
    shapes['mirror'] = R(20,5,88,95,'{fill}',15) + R(27,12,74,79,'{paper}',10) + P('M39 76 L77 24 M56 79 L84 40 M64 100 L64 116 M42 119 L86 119',stroke='{accent}',width=4)
    shapes['bow_hands'] = shapes['heart'] + P('M7 84 Q24 72 46 52 M121 84 Q104 72 82 52',stroke='{paper}',width=12)
    shapes['arrow'] = P('M15 109 L102 22 M87 19 L106 18 L107 38',stroke='{fill}',width=6)
    shapes['bandana'] = P('M12 19 L116 19 L64 111Z','{fill}') + P('M15 27 L64 90 L113 27',stroke='{accent}',width=3)
    shapes['shrug'] = P('M38 23 L53 19 L45 43 L45 61 L83 61 L83 43 L75 19 L90 23 L112 56 L99 83 L82 64 L46 64 L29 83 L16 56Z','{fill}')
    shapes['straw'] = P('M49 119 L78 28 L104 27',stroke='{fill}',width=9) + P('M74 39 L84 43 M77 29 L87 33',width=2)
    shapes['branch'] = P('M23 119 L60 65 L67 5 M56 74 L12 38 M59 69 L109 42 M60 40 L32 18 M66 20 L96 10',stroke='{fill}',width=7)
    shapes['lace'] = ''.join(C(x,y,11,'none') for x in (20,49,78,107) for y in (23,53,83)) + P('M9 108 q8 20 16 0 q8 20 16 0 q8 20 16 0 q8 20 16 0 q8 20 16 0 q8 20 16 0 q8 20 16 0',stroke='{fill}',width=3)
    shapes['zipper'] = ''.join(R(x,y,17,9,'{fill}',1) for i,y in enumerate(range(12,120,13)) for x in ([47] if i%2 else [64])) + R(49,33,31,24,'{accent}') + R(57,44,15,37,'{paper}')
    shapes['confetti'] = ''.join(f'<g transform="rotate({(i*37)%180} {x} {y})">{R(x,y,8,17,c,0)}</g>' for i,(x,y,c) in enumerate(((18,22,'#dd646a'),(48,15,'#f1ce61'),(86,28,'#579bd4'),(18,67,'#68c7ca'),(61,51,'#a48bcf'),(100,73,'#6aa780'),(38,95,'#e997bd'),(73,100,'#e89954'))))
    shapes['pumpkin'] = P('M63 27 Q8 5 10 74 Q8 117 63 118 Q120 117 118 74 Q120 5 63 27Z','{fill}') + P('M64 28 L64 10 L82 5',stroke='{accent}',width=7) + P('M31 54 L49 70 L28 75Z M97 54 L79 70 L100 75Z M34 90 L48 93 L56 86 L64 96 L72 86 L80 93 L94 90 L82 105 L46 105Z','{ink}')
    shapes['fan'] = P('M10 48 Q64 -6 118 48 L64 114Z','{fill}') + P('M64 114 L29 30 M64 114 L50 18 M64 114 L78 18 M64 114 L99 30',width=2)
    shapes['axe'] = P('M27 119 L87 9',stroke='{accent}',width=9) + P('M53 36 L85 44 L113 42 Q114 80 82 88 L54 55Z','{fill}')
    shapes['scythe'] = P('M72 121 L57 19',stroke='{accent}',width=8) + P('M16 21 Q104 -7 117 89 Q98 37 21 39Z','{fill}')
    shapes['dagger'] = P('M64 4 L82 72 L64 84 L46 72Z','{fill}') + P('M35 85 L93 85 M64 85 L64 122',stroke='{accent}',width=7)
    shapes['flag'] = P('M24 121 L24 7',stroke='{accent}',width=6) + P('M27 10 Q69 -1 110 23 L102 81 Q62 57 27 74Z','{fill}')
    shapes['basket'] = P('M14 63 L114 63 L102 113 L26 113Z','{fill}') + P('M31 63 Q31 4 64 6 Q97 4 97 63 M23 82 L109 82 M29 99 L104 99 M40 66 L43 112 M64 66 L64 113 M88 66 L85 112',width=3)
    shapes['bucket'] = P('M25 34 L103 34 L94 115 L34 115Z','{fill}') + P('M28 63 Q4 10 64 10 Q124 10 100 63',stroke='{accent}',width=4)
    shapes['candle'] = R(40,41,48,78,'{fill}') + P('M39 41 Q46 52 51 41 Q57 59 64 41 Q71 54 77 41 Q83 51 89 41','{accent}') + P('M64 6 Q34 33 64 38 Q88 35 64 6Z','#e89954')
    shapes['teapot'] = P('M31 49 Q17 113 66 119 Q114 113 96 49Z','{fill}') + P('M28 64 L7 32 L7 74 L26 91 M99 59 Q130 56 116 93 L98 105 M29 47 Q65 21 100 47Z','{accent}') + C(65,29,8)
    shapes['clock'] = C(64,64,53,'{paper}') + P('M64 21 L64 64 L93 76 M64 14 L64 22 M64 106 L64 114 M14 64 L22 64 M106 64 L114 64',width=4)
    shapes['gear'] = C(64,64,39) + C(64,64,18,'{paper}') + ''.join(P('M59 11 L69 11 L69 27 L59 27Z','{fill}') if i==0 else f'<g transform="rotate({i*45} 64 64)">{R(59,9,10,19)}</g>' for i in range(8))
    shapes['blanket'] = P('M14 15 L107 15 L113 96 Q86 84 84 113 L19 113Z','{fill}') + P('M86 113 L113 96 M26 35 L91 35 M26 53 L91 53 M26 71 L91 71',stroke='{accent}',width=2)
    shapes['bench'] = R(7,65,114,21) + R(7,18,114,33) + P('M20 51 L20 114 M108 51 L108 114',width=6)
    shapes['pool'] = P('M7 55 L79 20 L121 60 L50 107Z','{fill}') + P('M24 63 Q42 46 61 59 Q80 72 103 52 M64 91 L78 47 M75 96 L89 52 M70 62 L83 66 M67 74 L80 78',stroke='{paper}',width=4)
    shapes['road'] = P('M41 8 L87 8 L119 119 L9 119Z','{fill}') + P('M64 19 L64 40 M64 59 L64 82 M64 101 L64 119',stroke='{paper}',width=5)
    shapes['field'] = P('M7 118 L7 57 Q64 8 121 57 L121 118Z','{fill}') + P('M64 53 L24 115 M77 53 L65 115 M88 53 L108 115',stroke='{accent}',width=3)
    shapes['classroom'] = R(10,12,108,51,'{fill}') + P('M24 37 L97 37 M24 48 L83 48',stroke='{paper}',width=3) + R(15,84,42,15,'{accent}') + R(71,84,42,15,'{accent}') + P('M20 99 L20 121 M52 99 L52 121 M76 99 L76 121 M108 99 L108 121',width=4)
    shapes['eyeball'] = C(64,64,49,'{paper}') + C(64,64,29) + C(64,64,13,'{ink}')
    shapes['pom_pom'] = ''.join(P(f'M64 64 L{x} {y}',stroke='{fill}',width=8) for x,y in ((14,30),(32,9),(67,7),(104,14),(119,51),(111,93),(74,117),(36,111),(10,85),(7,54))) + C(64,64,20,'{accent}')
    shapes['mittens'] = P('M31 118 L20 74 Q2 61 9 49 Q23 38 34 65 L34 24 Q38 6 58 12 L80 12 Q99 13 102 36 L97 118Z','{fill}')
    shapes['wine_glass'] = P('M30 9 L98 9 L94 49 Q92 73 64 77 Q36 73 34 49Z','{paper}') + P('M36 40 L92 40 Q91 67 64 70 Q37 67 36 40Z','{fill}') + P('M64 77 L64 112 M37 119 L91 119',width=5)
    shapes['pixel_person'] = ''.join(R(x,y,16,16,'{fill}',0) for x,y in ((48,8),(64,8),(48,24),(64,24),(48,44),(64,44),(48,60),(64,60),(16,44),(32,44),(80,44),(96,44),(48,76),(64,76),(32,92),(80,92),(32,108),(80,108)))
    return shapes


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def definition_rows(directory: Path):
    for name in ('terms.tsv', 'long_tail.tsv'):
        with (directory / name).open(encoding='utf-8', newline='') as source:
            yield from csv.DictReader(source, delimiter='\t')


def build(root: Path = ROOT) -> dict:
    directory = root / 'resources' / 'tag_visuals'
    directory.mkdir(parents=True, exist_ok=True)
    shapes = primitives()
    terms = {}
    references = {}
    for row in definition_rows(directory):
        if None in row:
            raise ValueError(f'Extra TSV fields in definition: {row.get("name")}')
        row = {k: (v or '').strip() for k, v in row.items()}
        name = canonical_tag_key(row['name'])
        group, shape = row['group'], row['shape']
        if name in terms or shape not in shapes or not row['zh']:
            raise ValueError(f'Duplicate term / unknown primitive / missing Chinese: {name} / {shape}')
        status = row.get('status') or 'direct'
        terms[name] = {
            'group': group, 'label_zh': row['zh'],
            'explanation_zh': row.get('explanation') or (row['zh'] + '。'),
            'status': status, 'recipe': {'shape':shape, 'family':shape if shape in {'hair','eyes','face','body','pose'} else 'object',
                                       'variant':row['name'], 'features':(row.get('features') or '').split(',') if row.get('features') else []},
            'reason': '图示只作类别提示，具体含义采用文字说明。' if status == 'category_only' else '',
        }
        references[name] = row.get('reference') or 'project-curated definition'
        features = terms[name]['recipe']['features']
        if 'two-tone' in features:
            terms[name]['recipe'].update(color='#926447',accent='#e997bd')
        if name.startswith('holding '):
            features.append('held')
        if name.startswith('dark skin') or name.startswith('dark-skinned') or name == 'tan':
            terms[name]['recipe']['color'] = '#926447'
        elif name in {'pale skin','white skin'}:
            terms[name]['recipe']['color'] = '#f1d9c8'
        if name in {'blood','blood on face','blood on clothes'}:
            terms[name]['recipe']['color'] = '#dd646a'
        if name == 'white pupils':
            terms[name]['recipe']['color'] = '#ffffff'
        if name == 'black-framed eyewear':
            features.append('black-frame')
        if 'count' == shape:
            raise ValueError('Use person with numeric recipe count')
    for n in range(1,7):
        for suffix,label in (('girl','女性人物'),('boy','男性人物'),('other','其他性别人物')):
            key = f'{n}{suffix}' + ('s' if n>1 and suffix != 'other' else '')
            terms[key] = {'group':'object','label_zh':f'{n}位{label}','explanation_zh':f'画面中有{n}位{label}；表示人数，不表示年龄。',
                          'status':'schematic','recipe':{'shape':'person','count':n,'count_label':str(n)},'reason':''}
    for key,label in (('multiple girls','多位女性人物'),('multiple boys','多位男性人物'),('6+girls','至少六位女性人物'),('6+boys','至少六位男性人物')):
        terms[key] = {'group':'object','label_zh':label,'explanation_zh':label+'；表示人数，不表示年龄。','status':'schematic','recipe':{'shape':'people','count':6 if key.startswith('6') else 3,'count_label':'6+' if key.startswith('6') else '2+'},'reason':''}
    modifiers = {k:{'zh':v[0],'feature':v[1],'groups':'clothing,object,scene'} for k,v in MODIFIERS.items()}
    for key in ('long','short','two-tone','wet','shiny','wide','low','high','asymmetrical'):
        if key in modifiers:
            modifiers[key]['groups'] += ',hair,eyes,body'
    for key in ('fishnet','polka-dot','fur trim','two tone','see through','star print','heart print','gradient'):
        aliases = {'fishnet':('网格','fishnet'), 'polka-dot':('圆点纹','polka-dot'), 'fur trim':('毛绒边','fur-trim'),
                   'two tone':('双色','two-tone'), 'see through':('透视材质','transparent'), 'star print':('星形印花','star-pattern'),
                   'heart print':('爱心印花','heart-pattern'), 'gradient':('渐变色','gradient')}
        zh, feature = aliases[key]
        modifiers[key] = {'zh':zh,'feature':feature,'groups':'clothing,object,scene,hair,eyes'}
    for name,(zh,color) in COLORS.items():
        modifiers[name+'-trimmed'] = {'zh':zh+'边饰','feature':'color-trim','color':color,'groups':'clothing'}
    rules = {'schema_version':1,'sources':['https://safebooru.donmai.us/wiki_pages/tag_groups'], 'terms':terms,'colors':COLORS,'modifiers':modifiers}
    write_json(directory / 'rules.json',rules)
    write_json(directory / 'primitives.json',{'schema_version':1,'license':'Original project SVG diagrams, MIT; no upstream images copied.','shapes':shapes})
    library = TagVisualLibrary(directory, load_catalog=False)
    if not library.available:
        raise RuntimeError('Generated visual library failed validation')
    records = {}
    sources = []
    model_sources = set()
    for path in sorted((root / 'models').glob('*/selected_tags.csv')):
        model_sources.add(path.parent.name)
        sources.append({'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        for row in csv.DictReader(path.open(encoding='utf-8-sig',newline='')):
            category = {'0':'general','4':'character','9':'rating','3':'copyright'}.get(row['category'],'other')
            name = canonical_tag_key(row['name'])
            identity = category + ':' + name
            count = int(row.get('count') or 0)
            if identity not in records:
                records[identity] = {'name':row['name'],'category':category,'count':count,'sources':[path.parent.name]}
            else:
                records[identity]['count'] = max(records[identity]['count'],count)
                records[identity]['sources'].append(path.parent.name)
            for ip in json.loads(row.get('ips') or '[]'):
                ip_key = 'copyright:' + canonical_tag_key(ip)
                if ip_key not in records:
                    records[ip_key] = {'name':ip,'category':'copyright','count':0,'sources':[path.parent.name+' ips']}
    # Include the actual supported prompt/negative presets, without embedding
    # any user's settings or manual prompt contents in shipped resources.
    preset_files = []
    for filename in ('prompt_profiles.json','negative_presets.json'):
        path = root / 'resources' / filename
        payload = json.loads(path.read_text(encoding='utf-8'))
        preset_files.append({'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        names = ([tag for profile in payload['profiles'].values() for tag in profile.get('prefix_tags',[])]
                 if 'profiles' in payload else [tag for tags in payload['presets'].values() for tag in tags]+payload.get('defect_tags',[]))
        for tag in names:
            key = 'general:'+canonical_tag_key(tag)
            records.setdefault(key,{'name':tag,'category':'general','count':0,'sources':[]})
            records[key]['sources'].append(filename)
    # Include original curated terms so manual tags work without models.
    for name in terms:
        records.setdefault('general:'+name,{'name':name,'category':'general','count':0,'sources':['curated definitions']})
    entries={}; ledger=[]
    refinement_path = directory / 'refinements.json'
    refinements = {}
    if refinement_path.is_file():
        refinement_data = json.loads(refinement_path.read_text(encoding='utf-8'))
        if refinement_data.get('schema_version') != 1:
            raise ValueError('Unsupported visual refinement schema')
        refinements = refinement_data['entries']
        if set(refinements) - set(records):
            raise ValueError('Refinement refers to an unknown category/name')
    for identity,record in sorted(records.items()):
        category=record['category']; name=record['name']
        visual=library.lookup(name,category) if category in {'character','copyright'} else library.compose(name,category)
        if identity in refinements:
            revision = refinements[identity]
            recipe = {**dict(visual.recipe or {}), 'refinement':'r1'}
            visual = replace(visual, recipe=MappingProxyType(recipe),
                             status=revision.get('status', visual.status),
                             explanation_zh=revision.get('explanation_zh', visual.explanation_zh),
                             reason='' if revision.get('status') else visual.reason)
            references[visual.key] = 'https://safebooru.donmai.us/wiki_pages/' + name.replace(' ', '_')
        recipe=dict(visual.recipe) if visual.recipe else None
        if recipe and isinstance(recipe.get('features'),tuple): recipe['features']=list(recipe['features'])
        entries[identity]={'group':visual.group,'label_zh':visual.label_zh,'explanation_zh':visual.explanation_zh,
                           'status':visual.status,'recipe':recipe,'reason':visual.reason}
        reference = references.get(visual.key, 'verified term composition' if visual.semantic else 'proper-name category' if category=='copyright' else 'unreviewed')
        ledger.append({**record,'key':identity,'group':visual.group,'status':visual.status,'label_zh':visual.label_zh,
                       'explanation_zh':visual.explanation_zh,'reason':visual.reason,'reference':reference,
                       'visual_method':str(recipe.get('shape','')) if recipe else ''})
    top=sorted((r for r in ledger if r['category']=='general' and r['count']>0),key=lambda r:(-r['count'],r['key']))[:1000]
    supported=sum(r['status'] in SEMANTIC_STATUSES for r in top)
    model_rows = [r for r in ledger if r['category']=='general' and any(s in model_sources for s in r['sources'])]
    definition_paths = [directory/'terms.tsv', directory/'long_tail.tsv']
    if refinement_path.is_file():
        definition_paths.append(refinement_path)
    summary={'schema_version':1,'source_files':sources,'preset_files':preset_files,
             'definition_files':[{'path':p.relative_to(root).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in definition_paths],
             'terms':len(terms),'primitives':len(shapes),
             'model_general_tags':len(model_rows),'model_general_statuses':dict(Counter(r['status'] for r in model_rows)),
             'all_statuses':dict(Counter(r['status'] for r in ledger)),
             'non_character_statuses':dict(Counter(r['status'] for r in ledger if r['category']!='character')),
             'top_1000':{'semantic':supported,'total':len(top),'percent':round(supported/max(len(top),1)*100,2),
                         'gaps':[r for r in top if r['status'] not in SEMANTIC_STATUSES]},
             'by_group':{g:dict(Counter(r['status'] for r in ledger if r['group']==g)) for g in sorted({r['group'] for r in ledger})}}
    write_json(directory / 'catalog.json',{'schema_version':1,'entries':entries})
    write_json(directory / 'coverage.json',summary)
    with (directory/'coverage.tsv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['key','name','category','count','group','status','label_zh','explanation_zh','visual_method','reason','reference','sources'],delimiter='\t')
        w.writeheader()
        for r in ledger:
            r=dict(r);r['sources']='; '.join(r['sources']);w.writerow(r)
    print(json.dumps({k:v for k,v in summary.items() if k not in {'source_files','by_group','top_1000'}},ensure_ascii=False))
    print(json.dumps({k:v for k,v in summary['top_1000'].items() if k!='gaps'},ensure_ascii=False))
    print('High-frequency gaps: '+', '.join(r['name'] for r in summary['top_1000']['gaps']))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    build(parser.parse_args().root)
