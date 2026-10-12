"""Audited definition families for compiling public Wiki evidence offline.

Each adapter recognizes a positive definition, not a tag-group membership. It
records the exact defining passage and the family which establishes ownership,
dependencies and conflicts. Disambiguations and unresolved role changes are
deliberately left in the work queue.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_rules import primitive


def plain(text):
    text = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]",
                  lambda m: m[2] or m[1].replace("_", " "), text)
    text = re.sub(r'"([^"\n]+)":\S+', r"\1", text)
    return re.sub(r"\[/?[^\]]+\]", "", text).strip()


def definition(body):
    """Read introductory prose; examples and See Also are never definitions."""
    lines = body.replace("\r", "\n").splitlines()
    prose = []
    for line in lines:
        line = line.strip()
        if re.match(r"h[1-6](?:#[\w-]+)?\.", line, re.I):
            break
        if line.startswith(("*", "!post", "!asset", "[expand", "[table", "|")):
            continue
        if line:
            prose.append(line)
        if len(prose) >= 3:
            break
    return "\n".join(prose)


@dataclass(frozen=True)
class Family:
    family: str
    slot: str
    heads: tuple[str, ...]
    adult: bool = False


# Narrow semantic heads. The phrase must occur in the defining noun phrase,
# or the page must define a property of this head with an explicit construction.
# A mention in a related-tags list or "unlike X" does not qualify.
FAMILIES = (
    Family("garment_outfit", "outfit", tuple("uniform|costume|outfit|dress|gown|robe|kimono|yukata|hakama outfit|cheongsam|qipao|bodysuit|swimsuit|bikini|suit|pajamas|tracksuit|overalls|jumpsuit|hanfu|furisode|sarafan|ao dai|dirndl|tunic|qixiong ruqun|ruqun|toga|cassock|surplice|habit|tabard|gakuran|sukajan|shihakushou|happi|deel|changshan|hakama set".split("|"))),
    Family("garment_top", "top", tuple("shirt|blouse|top|camisole|bustier|sweater|jersey|rash guard|pullover|turtleneck|singlet|corset|chemise|undershirt|tank top|tube top|halter top|henley".split("|"))),
    Family("garment_bottom", "bottom", tuple("skirt|pants|shorts|trousers|jeans|bloomers|buruma|loincloth|sarong|kilt|hakama|culottes|hotpants|hot pants|capri pants|pantaloons".split("|"))),
    Family("garment_outer", "outerwear", tuple("jacket|coat|cape|cloak|shawl|poncho|mantle|cardigan|vest|waistcoat|blazer|haori|bolero|hoodie|sweatshirt|anorak|parka|hanten|pelisse|pelerine|windbreaker|sweat jacket".split("|"))),
    Family("garment_shoes", "footwear", tuple("footwear|shoes|shoe|boots|boot|sneakers|sneaker|sandals|sandal|slippers|slipper|loafers|loafer|moccasins|moccasin|heels|geta|zouri|zori|clogs|cleats|pumps|sabatons|espadrilles|ice skates|roller skates".split("|"))),
    Family("garment_head", "headwear", tuple("headwear|headgear|hat|cap|helmet|beret|bonnet|hood|headscarf|veil|headdress|crown|tiara|visor|turban|hijab|wimple|ushanka|coif|balaclava|honggaitou|tokin|sombrero|ushanka|diadem".split("|"))),
    Family("garment_legs", "legwear", tuple("legwear|socks|sock|stockings|stocking|thighhighs|pantyhose|tights|leggings|kneehighs|leg warmers|leg warmer|puttees|gaiters|greaves|tabi|over-kneehighs".split("|"))),
    Family("garment_hands", "handwear", tuple("handwear|gloves|glove|mittens|mitten|gauntlets|gauntlet|hand wraps|handwraps|vambraces|bracers".split("|"))),
    Family("worn_accessory", "accessory", tuple("accessory|accessories|jewelry|jewellery|ornament|hairpin|hair clip|hairclip|hairband|hair band|headband|hair tie|hair scrunchie|scrunchie|barrette|hair bobbles|ribbon|bow|hair beads|kanzashi|hair stick|hair tubes|hair tube|necklace|pendant|amulet|talisman|choker|collar|ascot|scarf|necktie|bowtie|neckerchief|belt|sash|obi|suspenders|garter belt|garter straps|bracelet|bangle|wristband|armband|armlet|anklet|cuffs|wrist cuffs|wristwatch|watch|ring|brooch|badge|medal|epaulettes|epaulette|pauldrons|shoulder armor|earrings|earring|piercing|nipple covers|pasties|sarashi|mask|face mask|goggles|eyewear|glasses|sunglasses|eyepatch|monocle|pince-nez|holster|harness|apron|waist apron|towel|neck bell|feather boa|stole|scabbard|sheath|headdress|arm strap|thigh strap|arm ribbon|ankle ribbon|ankle cuffs|thighlet|chest strap|shoulder guard|spats|shin guards".split("|"))),
    Family("underwear", "underwear", tuple("underwear|undergarment|undergarments|lingerie|bra|brassiere|panties|thong|g-string|g string|briefs|boxers|fundoshi|loincloth|babydoll|bodystocking|panty|petticoat|bandeau|underpants|jockstrap|boxer shorts|boxer briefs|bra top|sports bra|strapless bra|leotard|bunnysuit".split("|")), True),
    Family("hair_color", "hair.color", ("hair",)),
    Family("eye_color", "eyes.color", ("eyes", "eye")),
    Family("skin_color", "skin.color", ("skin",)),
    Family("hair_attribute", "hair.detail", tuple("hair|bangs|sidelocks|hair rings|ahoge|hair flaps|hair intakes|ponytail|twintails|braid|braids|bun|hair bun|updo|hair streaks|streaks|hair tips".split("|"))),
    Family("visible_body_part", "body.visible", tuple("body|head|face|forehead|neck|shoulders|shoulder|collarbone|arms|arm|armpits|armpit|hands|hand|fingers|finger|wrists|wrist|elbows|elbow|palms|palm|legs|leg|thighs|thigh|knees|knee|ankles|ankle|feet|foot|toes|toe|soles|sole|heels|heel|chest|back|waist|hips|hip|navel|stomach|midriff".split("|"))),
    Family("animal_ears", "body.ears", tuple("ears|ear|animal ears|fake animal ears|cat ears|rabbit ears|fox ears|wolf ears|dog ears|horse ears|pointy ears|elf ears|bear ears|tiger ears|lion ears|mouse ears|sheep ears|goat ears|cow ears|deer ears".split("|"))),
    Family("body_wings", "body.wings", ("wings", "wing")),
    Family("body_tail", "body.tail", ("tail", "tails")),
    Family("body_horns", "body.horns", ("horns", "horn", "antlers", "antler")),
    Family("body_skin_detail", "body.detail", tuple("scar|tattoo|birthmark|mole|freckles|bandage|bandaid|adhesive bandage|bandaids|scarification|facial mark|facial markings|facial marking|skin mark|body markings|markings|wrinkles|scales|scale|fur|fur coat|feathers|feather|body hair|armpit hair|chest hair|leg hair|arm hair|beard|mustache|moustache|stubble|goatee|sideburns|dimple|dimples|beauty mark|claws|claw|fingernails|toenails|nails|nail polish|halo|tentacles|tentacle|mechanical arms|prosthesis|prosthetic|prosthese|prosthetics|prosthetic limb|cybernetic implant|antennae|antenna|fang|fangs|teeth|tooth|tusks|tusk|talons|talon|hooves|hoof|cloven hooves|scutes".split("|"))),
    Family("body_shape", "body.shape", tuple("physique|build|body type|body shape|muscles|muscular body|muscular build|musculature|abdomen|belly|stomach|waist|hips|thighs|chest|breasts|breast|buttocks|butt|ass|navel|belly button|nipples|nipple|areola|areolae|vulva|penis|genitalia|genitals|groin|pubic hair|testicles|testicle|anus|clitoris|scrotum".split("|"))),
    Family("body_eyes", "eyes.detail", tuple("eyebrows|eyebrow|eyelashes|eyelash|pupils|pupil|sclera|sclerae|eyelids|eyelid|eyes|eye|third eye".split("|"))),
    Family("body_face", "face.detail", tuple("nose|noses|cheeks|cheek|lips|lip|tongue|mouth|chin|jaw|forehead|blush|saliva|drool|drooling|sweat|sweatdrop|tears|tear|nosebleed|facial feature|facial features".split("|"))),
    Family("background", "background", ("background", "backdrop")),
    Family("image_border", "border", ("border", "outline", "frame")),
    Family("clothing_pattern", "clothing.pattern", ("print", "pattern", "fabric pattern", "clothing pattern")),
    Family("image_symbol", "symbol", ("symbol", "emblem", "logo", "icon", "sign", "musical note", "musical notes", "insignia", "heraldic device")),
    Family("image_text", "text", ("text", "lettering", "speech bubble", "thought bubble", "caption", "dialogue bubble", "dialogue", "sound effect", "sound effects", "sfx", "signature", "watermark")),
    Family("image_style", "style", tuple("style|art style|artstyle|drawing style|painting style|artwork|medium|art medium|drawing|painting|illustration|sketch|shading|coloring|colouring|color palette|colour palette|filter|rendering technique|rendering method|art technique|drawing technique|animation|comic|webcomic|manga|panel comic|comic strip|animation technique|pixel art|visual effect|aesthetic|drawing error|anatomical error|artistic error".split("|"))),
    Family("scene_place", "location", tuple("room|bedroom|classroom|bathroom|kitchen|hallway|corridor|library|laboratory|office|restaurant|cafe|bar|tavern|inn|shop|store|market|mall|school|university|museum|gymnasium|gym|theater|theatre|cinema|studio|garage|warehouse|hangar|shed|church|cathedral|temple|shrine|sanctuary|castle|palace|fortress|fort|ruins|ruin|tower|street|road|alley|sidewalk|plaza|square|city|town|village|harbor|port|pier|dock|bridge|beach|shore|coast|island|forest|woodland|woods|jungle|mountain|hill|valley|canyon|cliff|cave|desert|meadow|plain|field|farm|garden|park|courtyard|playground|stadium|racetrack|racecourse|arena|aquarium|zoo|onsen|bathhouse|swimming pool|pool|hot spring|river|lake|waterfall|ocean|sea|pond|stream|brook|swamp|marsh|grotto|space station|space|outer space|rooftop|balcony|staircase|stairs|tunnel|underpass|train station|railway station|bus stop|train interior|car interior|subway|lobby|dormitory|dressing room|locker room|hospital|operating room|storeroom|stairwell|auditorium|movie theater|movie theatre|greenhouse|cemetery|graveyard|dungeon|prison|jail|amusement park|fountain|pagoda|ruined city".split("|"))),
    Family("scene_nature", "scene.detail", tuple("sky|cloud|clouds|fire|flame|flames|smoke|steam|fog|mist|rain|snow|ice|icicle|icicles|water|wave|waves|wind|sun|moon|star|stars|planet|planets|galaxy|nebula|aurora|rainbow|horizon|sunset|sunrise|dawn|dusk|tree|trees|grass|moss|plant|plants|flower|flowers|petal|petals|leaf|leaves|branch|branches|bush|shrub|vine|vines|bamboo|boulder|rock|rocks|sand|soil|dirt|puddle|snowflake|snowflakes|dust|lightning|meteor|meteorite|comet|constellation|constellations|sunbeam|sun rays|sunlight|starlight|moonlight|embers|spark|sparks|ripple|ripples|splash|splashes|water drops|water droplets|water drop|bubble|bubbles|foam|sea foam|seafloor|seabed|air bubble".split("|"))),
    Family("scene_structure", "scene.detail", tuple("building|buildings|wall|walls|floor|flooring|ceiling|roof|door|doors|gate|gates|window|windows|railing|railings|fence|fences|brick|bricks|tile|tiles|tatami|pavement|paving|gravel|beam|column|pillar|statue|sculpture|monument|gravestone|tombstone|arch|architecture|construction|infrastructure|interior|cityscape|landscape|scenery|track|tracks|train tracks|railroad tracks|runway|rock formation".split("|"))),
    Family("object_food", "object", tuple("food|dish|meal|snack|confectionery|confection|candy|dessert|fruit|vegetable|vegetables|berry|berries|apple|banana|orange|lemon|lime|peach|pear|pineapple|cherry|cherries|grapes|grape|strawberry|strawberries|raspberry|watermelon|melon|coconut|tomato|tomatoes|potato|potatoes|carrot|carrots|corn|pumpkin|mushroom|mushrooms|cake|cakes|cupcake|cupcakes|cookie|cookies|biscuit|biscuits|chocolate|lollipop|pastry|tart|pie|bread|sandwich|burger|hamburger|pizza|noodle|noodles|ramen|soba|udon|pasta|spaghetti|sushi|onigiri|rice|bento|meat|steak|sausage|sausages|hot dog|fried chicken|fish cake|fishcake|dumpling|dumplings|dango|mochi|pocky|pretzel|donut|doughnut|egg|eggs|omelette|pancake|pancakes|waffle|waffles|ice cream|popsicle|shaved ice|pudding|jelly|jam|honey|cheese|butter|cream|sugar|salt|sauce|condiment|garnish|soup|stew|curry|salad|drink|beverage|coffee|tea|juice|milk|soda|beer|wine|champagne|cocktail|alcohol|liquor|sake|bottle|can|carton".split("|"))),
    Family("object_equipment", "object", tuple("object|item|tool|utensil|instrument|musical instrument|weapon|gun|firearm|pistol|handgun|rifle|shotgun|revolver|machine gun|submachine gun|cannon|turret|missile|rocket|bomb|grenade|sword|blade|knife|dagger|katana|rapier|sabre|saber|polearm|spear|lance|halberd|scythe|trident|mace|axe|ax|hammer|bat|baseball bat|bow|crossbow|arrow|arrows|shuriken|kunai|shield|staff|wand|lightsaber|vehicle|car|automobile|truck|bus|train|locomotive|motorcycle|motorbike|bicycle|bike|scooter|skateboard|ship|boat|watercraft|aircraft|airplane|aeroplane|plane|helicopter|tank|spaceship|spacecraft|mecha|mech|robot|machine|computer|laptop|tablet|phone|smartphone|cellphone|telephone|camera|video camera|television|tv|monitor|screen|game console|controller|game controller|microphone|speaker|loudspeaker|headphones|earphones|keyboard|computer mouse|printer|battery|cable|wire|light bulb|bulb|lamp|lantern|candle|flashlight|torch|sign|flag|banner|furniture|table|chair|bench|stool|bed|sofa|couch|desk|shelf|bookshelf|cabinet|dresser|wardrobe|book|notebook|magazine|newspaper|map|scroll|poster|paper|card|playing card|letter|envelope|document|ticket|passport|money|coin|coins|banknote|banknotes|banknote bundle|wallet|purse|bag|backpack|pouch|handbag|suitcase|briefcase|box|crate|container|basket|bucket|bowl|plate|cup|mug|glass|goblet|teacup|teapot|kettle|spoon|fork|chopsticks|tray|lunch box|thermos|pot|pan|saucepan|frying pan|cooking pot|toy|doll|puppet|plushie|stuffed toy|stuffed animal|teddy bear|ball|marble|marbles|dice|die|board game|chess piece|jigsaw puzzle|puzzle piece|game piece|sports equipment|racket|racquet|guitar|violin|viola|cello|piano|flute|trumpet|drum|drums|harp|lyre|saxophone|trombone|accordion|synthesizer|harmonica|recorder|euphonium|tuba|bass guitar|electric guitar|acoustic guitar|metronome|rope|chain|chains|leash|handcuffs|shackles|lock|padlock|key|keys|comb|hairbrush|hair brush|hair dryer|toothbrush|toothpaste|brush|paintbrush|palette|pen|pencil|eraser|marker|crayon|chalk|quill|fountain pen|marker pen|paint|ink|scissors|sewing needle|needle|thread|spool|tape|tape measure|ruler|tissue|tissues|handkerchief|napkin|napkins|mirror|compact|lipstick|cosmetics|makeup|broom|mop|rake|shovel|spade|watering can|trowel|hoe|sickle|saw|chainsaw|drill|wrench|screwdriver|pliers|anvil|nail|nails|screw|screws|wheel|tire|tyre|gear|cog|clock|hourglass|watch|umbrella|parasol|hand fan|fan|bell|wind chime|gift|present|gift box|ribbon|bouquet|branch|leaf|flower|feather|crystal|gem|jewel|stone|pebble|shell|seashell|bone|skull|skeleton|wreath|balloon|firework|fireworks|snow globe|idol|ofuda|gohei|yin yang orb|orb|talisman|scroll|potion|flask|jar|urn|vase|bust|figurine|figure|statue|model|telescope|binoculars|magnifying glass|microscope|glass vial|vial|syringe|test tube|medical equipment|crutch|crutches|cane|walking stick|wheelchair|stretcher|mask|respirator|oxygen mask|oxygen tank|gasmask|gas mask|cigarette|cigar|smoking pipe|lighter|match|matches|ashtray|pillow|cushion|blanket|quilt|towel|curtains|curtain|bed sheet|bedsheet|sheet|carpet|rug|mat|sponge|soap|bath sponge|bathtub|sink|toilet|urinal|shower|washbasin|screwdriver|hair iron|curling iron|straightening iron|flat iron|helmet|armor|armour|rigging|turret|mechanical arm|diploma|medal|trophy|podium|clipboard|easel|canvas|canvas stand|cone|traffic cone|traffic light|road sign|megaphone|remote control|antenna|antennae|dish antenna|satellite dish|fishing rod|fishing pole|fishing reel|fishing net|net|fishing lure|fish hook|fishing hook|fishhook|lifebuoy|swim ring|float|inflatable|floatie|ladder|stepladder|flash drive|usb drive|disc|compact disc|cd|dvd|record|vinyl record|video tape|cassette|cassette tape|floppy disk|film|photo|photograph|picture|painting|drawing|stamp|calendar|puppets|mask|platter|cutlery|tongs|spatula|rolling pin|whisk|ladle|measuring cup|grater|strainer|sieve|colander|baking pan|oven|stove|microwave|refrigerator|washing machine|vacuum cleaner|electric fan|air conditioner|heater|radiator|fire extinguisher|hose|sprinkler|chain link|spring|propeller|turbine|engine|motor|circuit board|circuit|chip|microchip|electronic component|laser|light stick|glowstick|glow stick|lightstick|penlight".split("|"))),
    Family("object_animal", "object", tuple("animal|bird|mammal|reptile|amphibian|fish|insect|bug|arachnid|arthropod|crustacean|mollusk|mollusc|cephalopod|creature|cat|kitten|dog|puppy|wolf|fox|rabbit|bunny|hare|horse|pony|donkey|mule|deer|elk|moose|reindeer|cow|bull|ox|calf|sheep|goat|lamb|pig|boar|bear|panda|raccoon|tanuki|badger|otter|weasel|ferret|stoat|hedgehog|squirrel|chipmunk|mouse|mice|rat|hamster|guinea pig|bat|lion|tiger|leopard|cheetah|jaguar|panther|elephant|rhinoceros|hippopotamus|giraffe|zebra|camel|llama|alpaca|monkey|ape|gorilla|orangutan|chimpanzee|sloth|koala|kangaroo|wallaby|platypus|seal|sea lion|walrus|dolphin|whale|orca|narwhal|shark|goldfish|koi|carp|salmon|tuna|eel|ray|manta ray|stingray|octopus|squid|cuttlefish|jellyfish|starfish|sea star|sea urchin|crab|lobster|crayfish|shrimp|prawn|snail|slug|clam|oyster|scallop|mussel|turtle|tortoise|crocodile|alligator|lizard|iguana|gecko|chameleon|snake|cobra|python|frog|toad|salamander|newt|dinosaur|dragon|wyvern|unicorn|pegasus|griffin|gryphon|phoenix|pigeon|dove|crow|raven|sparrow|swallow|robin|bluebird|canary|finch|parrot|parakeet|cockatoo|macaw|owl|eagle|hawk|falcon|vulture|seagull|gull|duck|goose|swan|chicken|rooster|chick|hen|turkey|peacock|penguin|flamingo|stork|crane|heron|pelican|ostrich|emu|kiwi|hummingbird|woodpecker|kingfisher|toucan|butterfly|moth|bee|bumblebee|wasp|hornet|ant|beetle|ladybug|ladybird|dragonfly|damselfly|grasshopper|locust|cricket|cicada|mantis|fly|mosquito|spider|scorpion|centipede|millipede|worm|earthworm|leech|caterpillar|silkworm|termite|cockroach|firefly|glowworm|slug|axolotl|capybara|chinchilla|red panda|sea otter|saber-toothed tiger|smilodon|megafauna|triceratops|tyrannosaurus|velociraptor|pterosaur|pterodactyl|manta|angelfish|clownfish|pufferfish|seahorse|sea dragon|chocobo|pokemon|pokémon|digimon|monster".split("|"))),
)


COLOR_WORDS = frozenset("aqua black blue brown green grey gray orange pink purple red white yellow blonde blond silver gold golden beige cream tan cyan teal magenta maroon navy violet lavender indigo turquoise vermilion platinum rainbow multicolored two-tone gradient split-color heterochromia light dark colored colourless colorless translucent transparent pale dark-skinned light-skinned grey-skinned green-skinned red-skinned blue-skinned purple-skinned pink-skinned".split())
HAIR_DETAILS = frozenset("bangs sidelocks locks ahoge cowlick hair intakes hair flaps hair strand hair strands hair streak hair streaks hair tuft hair tufts".split("|"))
ADULT = re.compile(r"\b(?:nude|naked|nudity|nipples?|areolae?|genitalia|genitals|penis|penises|vulva|vagina|pussy|anal|anus|clitoris|scrotum|testicles?|semen|ejaculat\w*|cum|precum|intercourse|penetrat\w*|orgasm|masturbat\w*|fellatio|blowjob|cunnilingus|sex\s+(?:act|toy|object|position)|sexual\s+(?:act|intercourse)|erotic|bondage|bdsm|lingerie|underwear|panties|thong|g-string|breast milk|lactat\w*|pubic|ahegao)\b", re.I)
UNRESOLVED = re.compile(r"^(?:ambiguous|deprecated|obsolete|invalid|do not use|not to be used)|\b(?:underage|prepubescent|pedophil\w*|loli\b|shota\b|toddler|child porn\w*|incest|rape|non-consensual|nonconsensual|bestiality)\b", re.I)


from dataclasses import replace

# Additional noun heads have the same physical ownership as their family.
EXTRA_HEADS = {
    'garment_outfit': 'attire|ensemble|clothing set|matching set|bikini set|one-piece garment|garments|unitard|leotard|bunnysuit|teddy|nightgown|negligee|nightdress|wedding dress|pinafore|pinafore dress|sundress|jumper dress|dressing gown|tuxedo|coverall|coveralls',
    'garment_top': 'upper garment|upper-body garment|torso garment|shirt-like garment|bodice|bralet|bikini top|crop top|blouson|guernsey|guayabera|dougi|dogi|topwear',
    'garment_bottom': 'lower garment|lower-body garment|bikini bottom|skort|skorts|bottomwear|britches|breeches|chaps|bermuda shorts|pant skirt',
    'garment_outer': 'outer garment|outerwear|overcoat|raincoat|peacoat|rain cape|capelet|waist cape|swimsuit cover-up|shrug|shrug garment|kesa|shoulder cape|cape collar',
    'garment_legs': 'leg coverings|leg covering|leg warmer|leg warmers|legguards|foot wraps|footwraps|footwear covers|sock-like garment|legwear garment',
    'garment_hands': 'arm warmers|arm warmer|arm guards|wrist guards|wrist guard|arm guard|forearm coverings|forearm covering|protective glove|wrist wrap|arm wrap',
    'garment_head': 'headgear|headcover|head covering|head covering garment|head garment|bridal headdress|mitre|miter|taqiyah|tubeteika|kippah|straw hat|fedora|bowler|top hat|cavalier hat|tricorne|tricorn|bicorne|bicorn|bucket hat|pillbox hat',
    'worn_accessory': 'strap|band|elastic band|strip of cloth|garter|arm garter|ankle garter|arm sling|sling|ear covers|ear cover|couter|neck bell|corsage|boutonniere|bib|blindfold|blindfold mask|sleep mask|visor|fan-shaped headdress|beads|tassel|tassels|chain accessory|neck ribbon|neck strap',
    'body_skin_detail': 'mole|moles|scars|tattoos|bandages|bandaids|skin creases|crease|creases|skin fold|skin folds|dimples|dimple|body fur',
    'scene_place': 'place|public location|residence|habitation|settlement|highway|freeway|motorway|expressway|avenue|passage|garden|residential building|apartment|hotel|motel|resort|boutique|restaurant interior|cabin|cottage|hut|campground|hammam|henge|structure',
    'scene_nature': 'fruits|plants|flora|vegetation|floral arrangement|floral arrangements|bloom|blossom|blossoms|rain droplets|water vapor|water vapour|vapor|vapour|dew|frost|contrail|steam cloud|dust cloud|galactic band|asteroid|asteroids|celestial body|astronomical body|star cluster|star clusters|shooting star|shooting stars|gas giant|gas planet',
    'object_equipment': 'device|appliance|apparatus|vessel|stopper|stand|launcher|projectile|munition|ammunition|container|product|peripheral|equipment|component|implement|utensil|garbage|rubbish|trash|packet|packets|medicine|drug|herb|drugs|reciprocating saw|handsaw|power tool|power tools|mallet|baton|telescope|hand mirror|dish|basin|cigarette holder|smoking accessory|binders|binder|ring binder|shield-like armament|artillery|water gun|springboard|fishing tackle|military equipment|furniture piece|musical instruments|board|chalkboard|whiteboard|blackboard|stop sign|handrail|armrest|hand rest|cake slice|fruit slice|fruit segment|paper strip|petal|petals|detached feathers',
    'object_animal': 'feline|canine|ungulate|rodent|marsupial|cetacean|invertebrate|vertebrate|marine invertebrates|songbird|seabird|waterbird|corvid|raptor|bovine|equine|equid|hominid|catfish|flatfish|hermit crab|sea slug|sea cucumber|fish species|bird species|rodents|lizards|snakes|invertebrates|vertebrates',
    'image_style': 'drawing medium|painting medium|illustration medium|traditional medium|digital medium|visual style|artistic style|artistic technique|visual technique|color scheme|colour scheme|composition technique|color contrast|colour contrast|composition|image composition|format|image format|layout|image layout|perspective|projection|viewpoint|drawing method|drawing technique|rendering|genre|art genre|fictional genre',
    'image_symbol': 'motif|printed motif|letter|character symbol|shape|geometric shape|geometry|hieroglyph|hieroglyphic character|diagram|chart|glyph|punctuation mark|punctuation symbol|text symbol',
    'image_text': 'message|phrase|inscription|word|words|text message|written message|advertisement|notice|username|artist name|web address|website address|URL|lettering|copyright notice',
}
FAMILIES = tuple(replace(family, heads=(*family.heads, *EXTRA_HEADS.get(family.family, '').split('|'))) if family.family in EXTRA_HEADS else family for family in FAMILIES)
HEAD_PATTERNS = {family.heads: re.compile(r"(?<![\w-])(?:" +
    "|".join(re.escape(head) for head in sorted(family.heads, key=lambda head: (-len(head), head))) +
    r")\s*$", re.I) for family in FAMILIES}


def _contains_head(text, heads):
    match = HEAD_PATTERNS[heads].search(text)
    return match.group(0).lower() if match else None


def _defining_phrase(text):
    # Definitions of types often start with "A kind of", "A form of", etc.
    if re.match(r"(?:when|holding|wearing|someone|a character|a person|a girl|a boy|characters|posts?|use|do not|deprecated|ambiguous|the act|the action)\b", text, re.I):
        return ""
    text = re.split(r'\.(?:\s|$)|\n', text, maxsplit=1)[0]
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"['\"]([\w -]+)['\"]", r'\1', text)
    # Named items often put the type after a copula: "The MG42 is a German
    # machine gun ...". Only a positive nominal definition is considered.
    if match := re.search(r"\b(?:is|are|refers to|denotes)\s+(?:an?|the|any|a type of|a kind of)\s+", text, re.I):
        text = text[match.end():]
    # Qualifiers describe the type, not a new noun head: "a small type of
    # earphones" and "a padded piece of fabric" retain their actual noun.
    text = re.sub(r'^(?:an?|the|any)\s+(?:(?:small|large|short|long|thin|flat|thick|padded|decorative|inset|traditional|distinct|special|particular|common|specific|certain)\s+){0,3}(?:type|kind|form|style|piece|pair|set|variant)\s+of\s+', '', text, flags=re.I)
    text = re.sub(r"^(?:(?:an?|the)\s+(?:type|kind|form|style|piece|pair|set)\s+of|an?|the|any|one|two|multiple|several)\s+", "", text, flags=re.I)
    text = re.sub(r"^(?:of\s+)?(?:a|an|the|numerous|various)\s+", "", text, flags=re.I)
    text = re.split(r"\b(?:that|which|who|whose|where|when|usually|typically|commonly|often|featuring|having|worn|used|depicting|showing|with|made|designed|consisting|placed|positioned|located|associated|attached|hanging|hangs|growing|appearing|taking|intended|describing|includes|seen|being|colored|coloured|belonging|for|of|to|on|in|at|over|under|behind|has|have|is|are|can|refers|represents|symbolizes|means|depicts|shows)\b|\.(?:\s|$)|[!?;:\n]", text, maxsplit=1, flags=re.I)[0]
    return text[:240].strip(" ,")


def _appearance_color(name, text, family):
    noun = {"hair_color": "hair", "eye_color": "eyes", "skin_color": "skin"}[family]
    tokens = set(name.replace("-", " ").split())
    if noun not in name or not tokens & COLOR_WORDS:
        return None
    if re.search(r"\b(?:print|ornament|accessory|doll|holding|covering|mouth|underwear|costume|on|over|under|alternate|blood|cum|pubic|armpit|chest|leg|arm|fur|bangs|streaks|tips)\b", name):
        return None
    positive = re.search(r"\b" + re.escape(noun) + r"\b.{0,65}\b(?:colou?r|black|blue|brown|green|grey|orange|pink|purple|red|white|yellow|blond|silver|gold|aqua|light|dark|tinted|gradient|two|multi)", text, re.I)
    positive = positive or re.search(r"\b(?:black|blue|brown|green|grey|orange|pink|purple|red|white|yellow|blond|silver|gold|aqua|light|dark|two-tone|multicolored|gradient)\b.{0,35}\b" + re.escape(noun) + r"\b", text, re.I)
    return positive


def infer_definition(name, page):
    """Return a typed rule with positive Wiki evidence, or a concrete gap reason."""
    raw = definition(page.get("body", ""))
    text = plain(raw)
    normalized = key(name)
    if not text:
        return None, None, "empty_definition"
    if UNRESOLVED.search(text) or UNRESOLVED.search(normalized):
        return None, None, "unresolved_or_restricted_definition"
    if normalized.startswith('unworn '):
        # Only the owned, source-checked prop adapter may interpret this prefix.
        # A generic garment family would falsely turn it into worn clothing.
        return None, None, 'unworn_garment_context_required'
    if re.search(r"\b(?:alternate|borrowed|official alternate|character parody|cosplay|genderswap|aged up|aged down)\b", normalized):
        return None, None, "identity_context_required"
    if re.search(r"\b(?:another|other person|other character|person's|someone else's)\b", normalized):
        return None, None, "ordered_participants_required"
    if re.search(r"\b(?:holding|grabbing|pulling|lifting|wearing|riding|licking|eating|drinking|carrying|covering|adjusting|touching|sitting|standing|lying|kneeling|bound|insert|insertion|sex|fingering|handjob|paizuri)\b", normalized):
        return None, None, "action_dependencies_required"
    if re.search(r"\b(?:biting|cleaning|bouncing|removed|removing|sheathed|unsheathed|aiming|pointing|hugging|cuddling|balancing|pull|lift|grab|hold|aside|partially|peek|peeking|rest|resting|support|between|behind|against|around|under|over|on|in|into|out of|from)\b", normalized):
        return None, None, "action_or_placement_dependencies_required"
    if not re.search(r"[a-z]", normalized):
        return None, None, "expression_adapter_required"
    positive = _defining_phrase(text)
    evidence = {"definition": text[:600], "passage": raw[:900]}
    # More specific noun families take precedence over generic object heads.
    for family in FAMILIES:
        if family.family in {"hair_color", "eye_color", "skin_color"}:
            head = _appearance_color(normalized, text[:300], family.family)
            if not head:
                continue
            if family.family == "worn_accessory" and head in {"bow", "ribbon", "ring", "ornament", "badge", "medal", "talisman", "amulet", "watch", "mask"} and not re.search(r"\b(?:worn|wear|wearing|jewelry|jewellery|fashion|hair|neck|finger|hand|ear|face|clothing|attire|costume|head|body|decorat)\w*\b", text[:400], re.I):
                continue
            noun = {"hair_color": "hair", "eye_color": "eyes", "skin_color": "skin"}[family.family]
            rule = primitive(name, family.slot)
            if set(normalized.split()) & {"two-tone", "multicolored", "gradient", "split-color", "rainbow"}:
                rule["provides"] = ["multicolor_hair" if noun == "hair" else "multicolor_eyes"] if noun != "skin" else []
        else:
            head = _contains_head(positive, family.heads)
            # Qualified heads need two independent observations: the actual tag
            # ends with the head, and introductory prose positively defines it.
            # This covers e.g. "sky-print shirt" even when its Wiki starts
            # "Clothing with a sky print ...". Lists and examples are excluded.
            tag_head = _contains_head(re.sub(r"\s*\((?:medium|object|weapon|clothes|pattern|symbol)\)$", "", normalized), family.heads)
            first_sentence = re.split(r'\.(?:\s|$)|\n', text, maxsplit=1)[0]
            if not head and tag_head and re.search(r"\b" + re.escape(tag_head) + r"\b", first_sentence, re.I) and not re.search(r"\b(?:not|without|rather than|instead of|unlike|different from)\b", first_sentence, re.I):
                head = tag_head
                evidence["construction"] = "qualified_name_and_positive_definition"
            if not head:
                # Direct adjective definitions, e.g. "Wings that are white" or
                # "A shirt with ..." still have the head in the subject.
                continue
            if family.family in {"visible_body_part", "hair_attribute"} and not tag_head:
                continue
            if family.family == "image_border" and not re.search(r"\b(?:border|outline|picture frame|frame)\b", normalized):
                continue
            if family.family in {"animal_ears", "body_wings", "body_tail", "body_horns"} and not re.search(r"\b(?:ears?|wings?|tails?|horns?|antlers?)\b", normalized):
                continue
            if family.family.startswith('garment_') and not tag_head and _contains_head(positive, family.heads) != head:
                continue
            if family.family == 'scene_place':
                if normalized in {'breaker gorgon', 'projectile cum'}:
                    continue
                if head == 'bar' and not re.search(r'\b(?:drink|alcohol|beer|wine|pub|tavern|establishment)\w*\b', first_sentence, re.I):
                    continue
            if family.family == "scene_place" and not re.search(r"\b(?:" + "|".join(re.escape(word) for word in family.heads) + r")\b", normalized):
                # Unnamed places require an explicit place noun as the complete
                # definition subject, e.g. "A bakery is a shop ...".
                if head in {'space', 'plain', 'field', 'bar', 'school', 'pool', 'structure', 'facility', 'site', 'place'}:
                    continue
            if family.family == "object_equipment" and head in {"picture", "drawing", "painting", "photo", "photograph", "model", "figure", "object", "item", "sign", "mask", "helmet", "armor", "armour", "robot", "mecha", "mech"} and not re.search(r"\b" + re.escape(head) + r"\b", normalized):
                continue
            if family.family in {"body_eyes", "body_face", "body_shape", "body_skin_detail"} and not re.search(r"\b(?:hair|eyes?|skin|nails?|horns?|wings?|tails?|ears?|breasts?|navel|tattoo|scar|fur|feet|hands?|legs?|arms?|nose|mouth|lips?|tongue|teeth|fangs?|blush|sweat|body|face|facial|cheek|beard|mustache|moustache|pupils?|sclera|eyebrow|eyelash|halo|tentacles?|claws?|hooves|hoof|areolae?|nipples?|penis|pussy|vulva|abs|hips|muscul|shoulder|genital|groin|pubic)\b", normalized):
                # A literal animal/object is not a feature on a human body.
                continue
            if family.family == "clothing_pattern" and re.search(r"\b(?:background|paper|book|art|hand|picture|paw|finger)\b", normalized):
                continue
            if family.family == "image_border" and head == "frame" and "frame" not in normalized and "border" not in normalized:
                continue
            if family.family == "garment_outfit" and re.search(r"\b(?:lift|pull|grab|hold|aside|upskirt|downblouse|naked)\b", normalized):
                continue
            slot = family.slot
            if family.family == "underwear":
                slot = "underwear.top" if head in {"bra", "brassiere", "bra top", "sports bra", "strapless bra", "bandeau"} else "underwear.bottom" if head in {"panties", "panty", "thong", "g-string", "g string", "briefs", "boxers", "fundoshi", "underpants", "jockstrap", "boxer shorts", "boxer briefs"} else "underwear"
            rule = primitive(name, slot, adult=family.adult)
            rule["head"] = head
            if family.family == "hair_attribute":
                rule["excludes"] = ["hair.length:bald"]
        rule["adult"] = rule["adult"] or bool(ADULT.search(text[:350]) or ADULT.search(normalized))
        evidence["family"] = family.family
        evidence["matched_head"] = head if isinstance(head, str) else head.group(0)
        return rule, evidence, ""
    return None, None, "definition_family_not_implemented"
