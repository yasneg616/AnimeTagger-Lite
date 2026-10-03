"""Original SVG redraws selected during the first local illustration review.

Only recipes explicitly carrying refinement=r1 use these drawings. Keeping
this layer separate preserves illustrations outside the accepted rework list.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re


def p(d: str, fill: str = "none", stroke: str = "{ink}", width: float = 2.5) -> str:
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'


def c(x: float, y: float, r: float, fill: str = "{fill}", stroke: str = "{ink}", width: float = 2.5) -> str:
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'


def rect(x: float, y: float, w: float, h: float, fill: str = "{fill}", radius: float = 4) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{{ink}}" stroke-width="2.5"/>'


def arrow(x1: float, y1: float, x2: float, y2: float) -> str:
    angle = math.degrees(math.atan2(y2-y1, x2-x1))
    return p(f'M{x1} {y1} L{x2} {y2}', stroke='{accent}', width=3) + f'<g transform="translate({x2} {y2}) rotate({angle})">{p("M-6 -4 L0 0 L-6 4",stroke="{accent}",width=3)}</g>'


def flower(x: float, y: float, radius: float, *, sakura: bool = False, fill: str = "{accent}") -> str:
    petal = ('M0 0 C-11 -12 -16 -26 -9 -30 L0 -25 L9 -30 C16 -26 11 -12 0 0Z' if sakura
             else 'M0 0 C-22 -15 -12 -34 0 -28 C12 -34 22 -15 0 0Z')
    body = ''.join(f'<g transform="rotate({i*72})">{p(petal,fill,width=1.5)}</g>' for i in range(5))
    body += c(0,0,5,'#f1ce61',width=1.5)
    return f'<g transform="translate({x} {y}) scale({radius/30})">{body}</g>'


def _outline(path: str) -> list[tuple[float, float]]:
    """Flatten these absolute SVG curves for portable filled pattern pieces.

    Qt's SVG Tiny renderer does not support clipPath consistently. Pattern
    geometry is trimmed here instead of relying on a browser-only clip.
    """
    tokens = iter(re.findall(r'[MLQCZ]|-?\d+(?:\.\d+)?', path))
    points = []
    x = y = 0.0
    for command in tokens:
        if command == 'Z':
            break
        if command in {'M', 'L'}:
            x, y = float(next(tokens)), float(next(tokens))
            points.append((x, y))
        elif command in {'Q', 'C'}:
            controls = [(x, y)]
            controls += [(float(next(tokens)), float(next(tokens))) for _ in range(2 if command == 'Q' else 3)]
            for step in range(1, 25):
                t = step / 24
                if command == 'Q':
                    weights = ((1-t)**2, 2*(1-t)*t, t*t)
                else:
                    weights = ((1-t)**3, 3*(1-t)**2*t, 3*(1-t)*t*t, t**3)
                points.append(tuple(sum(w*point[axis] for w,point in zip(weights,controls)) for axis in (0,1)))
            x, y = controls[-1]
        else:
            raise ValueError('Unsupported refinement outline command')
    return points


def _trim(points: list[tuple[float, float]], a: float, b: float, limit: float) -> list[tuple[float, float]]:
    """Keep the half-plane a*x + b*y <= limit."""
    output = []
    if not points:
        return output
    previous = points[-1]
    previous_distance = a*previous[0] + b*previous[1] - limit
    for current in points:
        distance = a*current[0] + b*current[1] - limit
        if (distance <= 0) != (previous_distance <= 0):
            t = previous_distance / (previous_distance-distance)
            output.append((previous[0]+t*(current[0]-previous[0]), previous[1]+t*(current[1]-previous[1])))
        if distance <= 0:
            output.append(current)
        previous, previous_distance = current, distance
    return output


def _pattern_piece(outline: str, planes: tuple[tuple[float, float, float], ...], fill: str) -> str:
    points = _outline(outline)
    for a,b,limit in planes:
        points = _trim(points,a,b,limit)
    if len(points) < 3:
        return ''
    coordinates = ' '.join(f'{x:.3f},{y:.3f}' for x,y in points)
    return f'<polygon points="{coordinates}" fill="{fill}" stroke="none"/>'


@dataclass(frozen=True)
class Drawing:
    body: str
    consumed: frozenset[str] = frozenset()


def tail(variant: str, features: set[str]) -> Drawing:
    # The muted torso and hips make the attachment point explicit.
    context = c(35,22,11,'{paper}') + p('M26 37 Q36 33 46 39 L51 72 L23 72Z','#b9c5d6')
    context += p('M24 72 L50 72 L56 110 L43 110 L36 85 L30 110 L17 110Z','#b9c5d6')
    context += p('M26 41 L17 61 L22 76',width=4)
    paths = ['M48 75 C79 87 101 72 102 47 C103 25 120 25 120 41 C119 55 113 60 114 71 C107 105 74 112 48 87Z']
    if 'short' in features:
        paths = ['M49 74 Q81 66 83 83 Q74 99 49 87Z']
    elif 'long' in features:
        paths = ['M49 75 C96 123 125 97 116 65 C111 47 99 38 112 20 C93 15 85 43 97 61 C122 99 80 102 49 85Z']
    if 'rabbit' in variant:
        return Drawing(context + c(61,80,18,'{fill}') + p('M49 70 l5 4 M58 65 l1 6 M68 70 l-4 5',stroke='{paper}',width=2), frozenset(features))
    if 'horse' in variant:
        paths = ['M48 73 Q70 61 79 79 L74 119 L66 111 L58 119 L53 100Z']
    elif 'demon' in variant:
        paths = ['M48 76 Q91 105 96 51 L90 51 L101 23 L114 51 L104 51 Q102 118 48 88Z']
    elif 'fox' in variant or 'wolf' in variant:
        paths = ['M48 76 Q87 39 117 50 L112 64 L120 64 L111 79 L117 81 L98 99 L105 100 Q77 112 48 88Z']
    elif 'dragon' in variant:
        paths = ['M48 77 Q86 88 104 56 L102 40 L112 45 L117 24 L121 62 L111 66 L113 76 L100 80 L101 91 L84 93 L81 104 Q61 108 48 88Z']
    elif 'dog' in variant:
        paths = ['M48 74 Q75 82 86 65 Q89 46 106 48 Q122 57 110 72 Q105 82 97 78 Q114 99 91 107 Q62 106 48 87Z']
    elif 'cat' in variant:
        paths = ['M48 77 Q87 100 94 72 L92 39 Q89 24 103 24 Q115 27 109 39 L106 72 Q99 114 48 88Z']
    elif 'multiple' in variant:
        paths = ['M48 74 Q89 65 96 28 Q109 18 108 34 Q95 83 48 85Z',
                 'M49 79 Q96 78 116 62 Q129 63 120 74 Q92 101 48 88Z',
                 'M48 82 Q89 88 105 112 Q108 125 96 115 Q75 99 48 90Z']
    body = context
    for index, path in enumerate(paths):
        body += p(path,'{fill}')
        pattern = ''
        if 'striped' in features:
            pattern = ''.join(_pattern_piece(path,((.17,1,y+3.5),(-.17,-1,-y+3.5)),'{accent}') for y in (46,64,82,100,118))
        elif 'multicolored' in features:
            pattern = ''.join(_pattern_piece(path,((-1,0,-left),(1,0,right)),fill) for left,right,fill in ((48,75,'#dd646a'),(75,98,'#6aa780'),(98,128,'#579bd4')))
        elif 'two-tone' in features:
            pattern = _pattern_piece(path,((-1,0,-91),),'{accent}')
        elif 'fox' in variant:
            pattern = _pattern_piece(path,((-1,0,-97),),'{paper}')
        if pattern:
            body += pattern + p(path)
    if 'horse' in variant:
        body += p('M59 79 L59 104 M65 78 L63 110 M72 82 L68 110',width=1.5)
    if 'fake' in variant:
        body += p('M21 68 L49 68',stroke='{accent}',width=5) + rect(46,72,11,13,'{paper}',2)
    consumed = {'long','short','striped','multicolored','two-tone','multiple','fox','fluffy','spade','fake','hair','cat','dragon-tail'}
    return Drawing(body,frozenset(consumed))


def footwear(slipper: bool, unworn: bool = False) -> str:
    # Oblique side view: sole, exposed toes, instep strap, and open heel.
    sole = p('M15 87 Q36 95 55 79 Q74 67 91 64 Q114 59 120 74 Q114 92 91 98 L45 117 Q18 117 10 106Z','{fill}')
    sole += p('M12 102 Q35 113 55 99 L103 81 M16 105 Q38 114 53 105',width=2)
    foot = p('M25 86 L32 58 Q47 48 54 62 L55 77 Q85 61 104 63 Q117 67 110 77 L63 101 Q34 105 25 86Z','{paper}')
    foot += p('M86 69 l2 9 M95 67 l2 7 M103 68 l1 5',width=1.5)
    strap = p('M54 68 Q61 57 72 60 L86 80 L71 92 Q60 78 54 68Z','{fill}')
    if not slipper:
        strap += p('M24 73 L55 70 L60 86 L28 90Z','{fill}') + p('M27 74 L24 60 Q35 44 52 57 L56 70',stroke='{fill}',width=7)
        strap += rect(27,73,10,8,'{accent}',2)
    return sole + ('' if unworn else foot) + strap


def cheongsam() -> str:
    body = p('M53 9 L75 9 L77 23 L91 31 L99 47 L83 56 Q75 66 78 80 L94 117 L77 117 L77 91 L67 117 L35 117 L48 80 Q52 64 45 55 L29 47 L37 31 L51 23Z','{fill}')
    body += p('M54 12 L74 12 L74 23 L54 23Z','{fill}') + p('M72 23 Q72 38 83 41 L81 79',stroke='{accent}',width=2)
    body += p('M48 55 Q64 63 79 55 M77 91 L77 117',width=1.5)
    for y in (32,44,56):
        body += p(f'M72 {y} q4 -4 8 0 q-4 4 -8 0',stroke='{accent}',width=2)
    body += p('M77 94 L77 117 L70 117Z','{paper}',width=1)
    return body


def horse() -> str:
    body = p('M81 72 L96 72 L101 110 L90 110Z','{fill}')
    body += p('M19 60 Q29 45 52 51 L76 50 Q77 35 88 24 L91 11 L97 16 L98 29 L109 36 L118 49 L115 59 L103 61 L93 47 L90 73 L85 85 L88 115 L76 115 L71 83 L48 81 L44 115 L33 115 L35 81 L27 82 L23 115 L13 115 L17 78Z','{fill}')
    body += p('M83 29 Q74 36 72 55 L83 53 L87 38Z','{ink}') + p('M20 62 Q1 62 7 98 Q20 90 16 73Z','{ink}')
    body += c(99,38,2.5,'{ink}','none') + p('M104 53 L115 52 M15 108 L24 108 M34 108 L44 108 M77 108 L87 108 M90 103 L100 103',width=2)
    return body


def fist() -> str:
    return p('M13 114 L13 78 Q5 64 12 52 Q17 45 24 51 Q26 40 34 43 Q41 38 47 47 Q56 44 59 55 L58 79 L51 95 L49 114Z','{fill}') + p('M14 61 Q23 56 31 63 L40 72 Q43 78 37 82 L24 73 M26 51 L26 63 M36 47 L36 63 M47 49 L47 63 M25 89 L45 90',width=2)


def lower_body(name: str) -> str:
    if name == 'ass_visible_through_thighs':
        body = p('M20 12 Q64 2 108 12 L113 44 L96 119 L76 119 L79 87 L92 58 Q64 74 36 58 L49 87 L52 119 L32 119 L15 44Z','{paper}')
        body += p('M39 58 Q43 83 64 81 Q85 83 89 58 M64 66 L64 80',stroke='{fill}',width=4)
        body += c(64,77,24,'none','{accent}',3) + arrow(111,93,86,84)
        return body
    body = p('M34 10 Q64 18 94 10 L96 39 Q96 53 86 60 L92 117 L72 117 L64 72 L56 117 L36 117 L42 60 Q32 53 32 39Z','{paper}')
    body += c(64,29,2,'{ink}','none')
    if name == 'cameltoe':
        body += p('M34 38 Q64 47 94 38 L87 64 L65 80 L41 64Z','{fill}')
        body += p('M60 62 Q58 69 63 74 M68 62 Q70 69 65 74',width=2)
        body += c(64,69,20,'none','{accent}',3)
    else:
        body += p('M45 46 Q64 39 83 46 L65 65Z','#6d5147',width=1)
        for x,y in ((51,48),(58,46),(65,46),(73,47),(78,49),(56,53),(64,52),(71,53),(63,58)):
            body += p(f'M{x} {y} q-2 3 1 5',stroke='{paper}',width=1.3)
        body += c(64,53,22,'none','{accent}',3)
        if name.startswith('female'):
            body += c(110,18,6,'none',width=2) + p('M110 24 L110 38 M104 32 L116 32',width=2)
        elif name.startswith('male'):
            body += c(106,21,6,'none',width=2) + p('M111 16 L121 6 M113 6 L121 6 L121 14',width=2)
    return body


def refined_geometry(name: str, shape: str, variant: str, features: set[str], shapes: dict[str,str]) -> Drawing | None:
    name = name.replace(' ', '_')
    if shape == 'tail' or name == 'rabbit_tail':
        return tail(variant,features)
    if shape == 'sandals':
        return Drawing(footwear('slippers' in name, 'unworn' in features), frozenset({'unworn'}))
    if name in {'cheongsam','china_dress'}:
        return Drawing(cheongsam(),frozenset({'side-slit'}))
    if name == 'side_slit':
        body = p('M76 61 L90 60 L87 119 L73 119Z','{paper}')
        body += p('M34 13 L87 13 Q91 60 96 114 L81 114 L84 65 L69 114 L28 114 Q44 62 34 13Z','{fill}')
        body += p('M37 23 L88 23 M87 29 L84 65',width=1.8) + arrow(116,58,88,80)
        return Drawing(body,frozenset({'side-slit'}))
    if name == 'newsboy_cap':
        body = p('M18 77 Q9 52 29 37 Q64 10 100 40 Q121 63 106 79Z','{fill}')
        body += p('M20 77 Q65 91 106 78 L106 89 Q62 103 21 90Z','{fill}')
        body += p('M90 88 L116 92 Q112 103 84 97Z','{fill}')
        body += p('M62 29 Q35 44 23 75 M62 29 Q45 61 46 84 M62 29 Q74 59 76 85 M62 29 Q94 44 105 75',width=1.8) + c(63,29,3,'{accent}')
        return Drawing(body,frozenset({'puffy'}))
    if name == 'nurse_cap':
        body = p('M17 42 L31 22 L97 22 L112 42 L95 86 L33 86Z','{paper}')
        body += p('M17 42 L39 50 L33 86 M112 42 L89 50 L95 86 M33 78 L95 78',width=2)
        body += p('M57 37 L71 37 L71 48 L82 48 L82 62 L71 62 L71 73 L57 73 L57 62 L46 62 L46 48 L57 48Z','#dd646a',width=1.5)
        return Drawing(body,frozenset({'cross'}))
    if name == 'nurse':
        head = c(64,31,18,'{paper}') + p('M46 26 Q47 7 64 10 Q81 7 82 26',stroke='#6d5147',width=5)
        cap = p('M44 10 L84 10 L79 23 L49 23Z','{paper}') + p('M64 12 L64 19 M60 16 L68 16',stroke='#dd646a',width=3)
        uniform = p('M49 52 L64 61 L79 52 L96 66 L85 79 L77 72 L88 116 L40 116 L51 72 L43 79 L32 66Z','{paper}')
        uniform += p('M51 54 L58 69 L64 61 L70 69 L77 54 M64 71 L64 113',width=1.5) + rect(47,89,12,12,'{paper}',2) + rect(69,89,12,12,'{paper}',2)
        uniform += p('M78 73 L78 84 M73 78 L83 78',stroke='#dd646a',width=3)
        return Drawing(head+cap+uniform,frozenset({'cross'}))
    if name == 'ninja':
        body = p('M24 104 L100 25 M90 24 L108 39',stroke='#8493a6',width=5)
        body += p('M32 54 Q25 10 64 9 Q103 10 96 54 L86 65 L94 112 L34 112 L42 65Z','#353944')
        body += p('M32 54 L20 62 L33 62 L20 76 L39 69','#353944')
        body += p('M36 31 Q64 25 92 31 L88 47 L40 47Z','{paper}') + p('M40 54 L88 54 M48 63 L80 63',stroke='#8493a6',width=2)
        body += c(51,38,3,'{ink}','none') + c(77,38,3,'{ink}','none')
        body += p('M45 75 L82 68 M45 97 L84 97',stroke='#8493a6',width=3)
        return Drawing(body,frozenset({'mask'}))
    if name == 'hair_ornament':
        body = p('M28 63 Q17 13 64 12 Q110 13 100 65 L105 115 L23 115Z','#926447') + p('M37 48 Q33 89 64 99 Q95 89 91 48Z','{paper}')
        body += p('M30 52 Q35 18 64 23 Q93 18 98 51 L79 45 L65 54 L50 45Z','#926447')
        body += c(51,65,3,'{ink}','none') + c(77,65,3,'{ink}','none') + p('M57 82 Q64 86 71 82',width=2)
        body += flower(96,37,19,fill='{fill}') + p('M92 54 L108 51',stroke='{accent}',width=4)
        return Drawing(body)
    if name == 'lace':
        body = rect(14,20,100,78,'{paper}',0)
        for x in range(-45,100,16):
            start, end = max(0,(16-x)/64), min(1,(112-x)/64)
            if start >= end:
                continue
            for y1,y2 in ((22,94),(94,22)):
                body += p(f'M{x+64*start:.3f} {y1+(y2-y1)*start:.3f} L{x+64*end:.3f} {y1+(y2-y1)*end:.3f}',stroke='{fill}',width=1)
        for x,y in ((37,45),(91,45),(64,75)):
            body += flower(x,y,17,fill='{paper}')
        for x in range(24,113,18):
            body += p(f'M{x-9} 97 Q{x-9} 112 {x} 112 Q{x+9} 112 {x+9} 97','{paper}') + c(x,104,3,'{fill}','none')
        return Drawing(body)
    if name in {'floral_background','floral_print_bikini'}:
        if name == 'floral_background':
            body = rect(10,14,108,100,'{paper}')
            positions = ((28,32,12),(91,35,13),(39,81,14),(93,91,13))
        else:
            body = shapes['bikini']
            positions = ((43,38,8),(85,38,8),(64,90,9))
        for x,y,r in positions:
            body += flower(x,y,r)
        return Drawing(body,frozenset({'floral','print'}))
    if name == 'cherry_blossoms':
        body = p('M17 115 Q49 103 69 65 L97 26',stroke='#926447',width=4)
        body += flower(62,66,39,sakura=True,fill='#eaa4be') + flower(103,27,17,sakura=True,fill='#eaa4be')
        body += p('M31 103 Q9 78 27 77 Q45 80 31 103Z','#6aa780',width=1.5)
        return Drawing(body)
    if name in {'crescent','crescent_moon','night','red_moon'}:
        moon = p('M97 15 C48 7 18 38 20 75 C23 112 67 126 106 102 C75 108 48 83 46 56 C44 35 64 20 97 15Z','#f1ce61')
        if name == 'red_moon':
            moon = c(64,64,45,'{fill}') + c(48,49,9,'none','{accent}',2) + c(74,86,13,'none','{accent}',2) + c(87,46,5,'none','{accent}',2)
        elif name == 'night':
            moon = rect(8,8,112,112,'#24354f') + f'<g transform="translate(26 10) scale(.62)">{moon}</g>'
            moon += p('M23 26 L23 38 M17 32 L29 32 M105 79 L105 91 M99 85 L111 85',stroke='#f3f6ff',width=2) + p('M11 116 L11 101 L35 89 L51 103 L51 116 M80 116 L80 94 L106 94 L106 116','#4e617d')
        return Drawing(moon)
    if name == 'cross':
        return Drawing(p('M50 12 L78 12 L78 44 L113 44 L113 72 L78 72 L78 116 L50 116 L50 72 L15 72 L15 44 L50 44Z','{fill}'),frozenset({'cross'}))
    if name == 'anger_vein':
        body = p('M49 16 L49 39 Q49 49 39 49 L16 49 M79 16 L79 39 Q79 49 89 49 L112 49 M16 79 L39 79 Q49 79 49 89 L49 112 M112 79 L89 79 Q79 79 79 89 L79 112',stroke='#dd646a',width=7)
        return Drawing(body,frozenset({'cross'}))
    if name == 'horse':
        return Drawing(horse())
    if name == 'riding':
        body = f'<g transform="translate(3 25) scale(.88 .8)">{horse()}</g>'
        body += p('M47 64 Q62 61 75 66 L74 74 L49 74Z','{accent}') + c(59,18,10,'{paper}')
        body += p('M53 31 L67 31 L64 57 L51 61Z','{fill}') + p('M65 34 L75 47 L93 47 M52 57 L72 70 L70 93 M93 47 L92 63',width=4)
        return Drawing(body,frozenset({'person'}))
    if name == 'index_finger_raised':
        body = p('M36 114 L33 80 Q19 63 28 53 Q35 48 45 61 L44 19 Q44 7 53 8 Q62 8 61 20 L61 56 Q67 47 75 55 Q83 48 89 60 Q96 54 102 66 L97 90 L89 114Z','{fill}')
        body += p('M62 59 L62 76 M75 56 L75 76 M88 61 L88 77 M45 65 Q55 75 49 84 L35 77 M63 89 L86 89',width=2)
        return Drawing(body)
    if name == 'clenched_hands':
        return Drawing(fist() + f'<g transform="translate(128 0) scale(-1 1)">{fist()}</g>')
    if name == 'salute':
        body = c(64,25,13,'{paper}') + p('M50 47 Q64 37 78 47 L73 74 L55 74Z','{fill}')
        body += p('M50 48 L33 44 L50 24 M78 47 L85 64 L84 83 M58 74 L52 112 M69 74 L77 112',width=5)
        body += p('M48 23 L56 24 M49 27 L55 27',width=1.5)
        return Drawing(body,frozenset({'salute'}))
    if name == 'legs_up':
        body = p('M10 114 L116 114',width=1.5) + c(22,99,11,'{paper}')
        body += p('M35 91 L70 89 L80 99 L69 107 L34 107Z','{fill}')
        body += p('M70 93 L73 48 L68 17 M79 98 L96 56 L108 26 M68 17 L81 16 M108 26 L120 30 M38 105 L61 109',width=6)
        return Drawing(body)
    if name == 'looking_at_another':
        left = p('M11 113 Q11 75 31 75 Q51 75 52 113Z','{fill}') + p('M13 31 Q31 14 47 33 L46 43 L55 49 L46 55 L46 64 Q23 78 13 58Z','{paper}')
        right = p('M77 113 Q78 75 97 75 Q116 75 117 113Z','#b9c5d6') + c(97,45,21,'{paper}')
        left += c(42,43,2.5,'{ink}','none')
        right += c(88,43,2.5,'{ink}','none')
        return Drawing(left+right+arrow(53,44,81,44))
    if name == 'licking':
        body = c(54,54,39,'{paper}') + c(41,48,3,'{ink}','none') + c(67,48,3,'{ink}','none')
        body += p('M49 70 Q64 62 77 76 Q65 86 51 82Z','{ink}')
        body += c(106,78,13,'{fill}') + p('M106 91 L106 117',stroke='#b99168',width=4)
        body += p('M58 79 Q71 91 94 78 Q99 79 95 86 Q70 101 56 86Z','#e997bd',width=2)
        body += p('M69 88 L88 84',stroke='#af5a80',width=1.5)
        return Drawing(body)
    if name == 'sweat':
        body = p('M24 117 Q27 88 64 88 Q101 88 104 117Z','#b9c5d6') + c(64,51,35,'{paper}')
        body += c(51,54,3,'{ink}','none') + c(77,54,3,'{ink}','none') + p('M58 74 L70 74',width=2)
        for x,y in ((43,31),(92,48),(25,61)):
            body += p(f'M{x} {y} q-10 15 0 18 q10 -3 0 -18Z','#67bde3',width=1.5)
        return Drawing(body)
    if name == 'tentacles':
        body = p('M23 118 C11 91 13 67 26 51 C37 38 23 21 14 31 C8 36 16 43 23 39 C41 44 37 57 30 69 C23 85 37 101 39 118Z','{fill}')
        body += p('M52 118 C51 80 74 68 73 43 C72 27 66 17 77 13 C92 8 102 26 88 32 C81 37 76 27 82 24 C65 41 88 63 72 90 L70 118Z','{fill}')
        body += p('M85 118 C83 89 105 78 109 55 C112 42 99 40 96 49 C94 55 104 60 105 51 C125 53 116 82 105 92 L104 118Z','{fill}')
        for x,y in ((25,79),(28,93),(31,106),(69,45),(69,62),(62,86),(62,105),(105,71),(99,87),(95,105)):
            body += c(x,y,3,'{paper}',width=1)
        return Drawing(body,frozenset({'multiple'}))
    if name in {'ass_visible_through_thighs','cameltoe','pubic_hair','female_pubic_hair','male_pubic_hair'}:
        return Drawing(lower_body(name))
    if name == 'condom':
        body = rect(8,57,43,52,'{paper}',3) + c(29,80,13,'none','{fill}',4)
        body += p('M66 100 L66 35 Q65 20 79 18 L79 11 Q85 3 91 11 L91 18 Q104 20 104 35 L104 100Z','{paper}')
        body += p('M68 38 L68 96 M99 33 L99 91',stroke='{fill}',width=2)
        body += '<ellipse cx="85" cy="102" rx="26" ry="10" fill="{fill}" stroke="{ink}" stroke-width="2.5"/><ellipse cx="85" cy="101" rx="19" ry="5" fill="{paper}" stroke="{ink}" stroke-width="1.5"/>'
        return Drawing(body)
    return None
