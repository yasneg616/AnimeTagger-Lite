"""Specific visual concepts and dependency grammars beyond noun definitions."""
from __future__ import annotations
import re
from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_rules import primitive
from scripts.prompt_semantic_families import ADULT, UNRESOLVED, plain, definition
from scripts.prompt_semantic_attributes import APPAREL, PARTS

RULES = {}


def add(names, slot, **kwargs):
    for name in names.split('|'):
        RULES[key(name)] = primitive(name, slot, **kwargs)


add('christmas_lights|christmas_present|christmas_stocking|cigarette_pack|cleaning_rag|cloth|clothes_hanger|clothes_pin|container|cooler|core|cream_puff|croissant|puzzle|puzzle_piece|pull_cord|puppet_strings|puppy|radar|radio|ramune|recorder|rerebrace|couter|price_tag|chips_(food)|cosmos_(flower)|queen_(chess)|queen_(playing_card)|hand_fan|folding_fan|handheld_electric_fan|shower_head|lipstick_tube|drink_carton|bow_(music)|toy_gun|music_box|record_player|vinyl_record|magic_circle|plastic_bag|clothes_basket|billiard_ball|car_key|credit_card|spice|syrup|tofu|creamer|pasta_sauce', 'object')
add('railroad_crossing|racetrack|prison', 'location')
add('uneven_eyes|clock_eyes|spiral-only_eyes|upturned_eyes|downturned_eyes|evil_eyes|uneven_eyebrows|mark_under_both_eyes', 'eyes.detail')
add('monkey_ears|owl_ears', 'body.ears')
add('snake_tail|crocodilian_tail', 'body.tail')
add('cleft_chin|food_on_face|chocolate_on_face|bruise_on_face|paint_splatter_on_face|patchwork_skin|metal_skin|hip_bones|red_scales', 'body.detail')
# Marks whose own definition is "located on a person's <part>". They belong to
# the same body-detail slot as "scar on face" and claim no other subject, so no
# participating character or held prop is involved.
add('scar_on_arm|scar_on_hand|scar_on_leg|scar_on_breast', 'body.detail')
add('quad_drills|ponytail_with_braided_base', 'hair.style', excludes=('hair.length:bald',))
add('feather_trim|cow_print|criss-cross_straps|criss-cross_back-straps|racerback', 'clothing.detail')
add('chiton', 'outfit')
add('retrofuturism|recurring_image|recursion|projected_inset|rainbow_gradient|revealing_layer|user_interface|holographic_interface|absurdly_detailed_composition', 'style')
add('qr_code|circled_9|red_sun|footprints', 'symbol')
add('price_tag|circle_name|commissioner_name|vehicle_name|fanbox_username|credits_page|request_inset', 'text')
add('relaxing|resting', 'action')
add('recording', 'style', phrase='a recording viewfinder overlay')
add('lamppost', 'scene.detail')


add('wet|veins|forehead_mark|whisker_markings|median_furrow|joints|doll_joints|stitches|biceps|ribs|dimples_of_venus|kneepits|hairy|very_hairy|body_blush|bodypaint|body_paint|colored_extremities|skin_fangs|bite_mark|lipstick_mark|eyebrows|sideburns|whiskers|teardrop|claws|talons|beak|snout|animal_nose|pawpads|cat_paws|cat_tail|goatee|facial_hair|nosebleed|heavy_breathing|steaming_body|small_sweatdrop|flying_sweatdrops|aegyo_sal|scowl_lines|colored_skin|albino|shiny_fur|bushy_tail|fluffy_tail|paws|animal_feet|animal_hands|arthropod_limbs|fins|gills|head_fins|prosthesis|prosthetic_arm|prosthetic_leg|prosthetic_hand|amputee|one_armed|one_legged|eyeball', 'body.detail')
add('ass|butt_crack|buttocks|huge_ass|huge_breasts|bare_pectorals|large_pectorals|breasts_apart|breasts_squeezed_together|hanging_breasts|breast_hold|grabbing_own_breast|grabbing_own_ass|foreskin|clitoral_hood|partially_visible_vulva|perineum|fat_mons|crotch|bulge|cameltoe|areolae|areola|breasts_out|one_breast_out|pubic_hair_peek|cleft_of_venus', 'body.detail', adult=True)
add('large_tail|long_tail|fluffy_tail|bushy_tail|short_tail|thick_tail|thin_tail|prehensile_tail|tail_wagging|tail_raised|tail_between_legs', 'body.tail')
add('tiger_ears|lion_ears|bear_ears|deer_ears|cow_ears|rabbit_ears|mouse_ears|sheep_ears|goat_ears|squirrel_ears|raccoon_ears|fox_ears|dog_ears|wolf_ears|bat_ears|horse_ears|pointy_ears|tengumimi', 'body.ears')
add('antlers|oni_horns|curled_horns|curved_horns|ram_horns|swept-back_horns', 'body.horns')
add('horns|horn', 'body.horns')
add('tail', 'body.tail')
add('light_frown|blank_stare|completely_unamused|concentrating|crazy_smile|crazy_grin|seductive_smile|shouting|streaming_tears|turn_pale|sad|happy|serious|nervous|scared|surprise|worried_face|flustered_face|confused_face|smug_face|shy_face|tired|sleepy|sleepy_eyes|disgust|disgusted|disgusted_face|awkward_smile|annoyed|anger|determination|derp|shocked|shock|doubt|sobbing|screaming|pursed_lips|puffed_cheeks', 'expression')
add('aroused|aroused_nosebleed|orgasm|female_orgasm|male_orgasm|moaning|lewd|lewd_expression', 'expression', adult=True)
add('licking_lips|biting_own_lip|mouth_drool|saliva_trail|sideways_mouth|sanpaku|one-eyed|fang_out|fangs_out|toenail_polish|colored_teeth|colored_tongue', 'face.detail')
add('averting_eyes|looking_to_the_side|looking_ahead|looking_at_hand|looking_at_self|looking_at_own_hand', 'gaze')
add('braided_base|roots_(hair)|inverted_bob|shaved_head|shaved_hair|messy_bangs|side_part|middle_part|side-swept_bangs|inward_curl|outward_curl|inverted_hair|bowl_cut|hime_cut|wolf_cut|bob_with_side_tails|undercut|fauxhawk|mohawk|pompadour|afro|buzz_cut', 'hair.style', excludes=('hair.length:bald',))
add('hair_over_breasts|hair_over_shoulders|hair_over_one_shoulder|hair_between_breasts|parallel_hairclips|multiple_hairclips|multiple_hairpins|multiple_hair_bows|parallel_braids|parallel_twintails|floating_hair|unkempt|hair_floating|hair_over_mouth|hair_over_face|hair_over_nose', 'hair.detail', excludes=('hair.length:bald',))
add('breastplate|bracer|arm_guards|muneate|kote|kurokote|greaves|faulds|single_pauldron|shoulder_pads|shoulder_spikes|lanyard|neck_bell|neck_ring|neck_cuff|dog_tags|ear_covers|single_ear_cover|earpiece|headpiece|triangular_headpiece|tate_eboshi|traditional_bowtie|tie_clip|lapels|spaghetti_strap|spaghetti_straps|wristband|armband|headband|drawstring|name_tag|ear_tag|zipper_pull_tab|stud_earrings|multiple_earrings|multiple_rings|pince-nez|under-rim_eyewear|bespectacled|furry_mask|beads|corsage|flower_knot|heart_of_string|tasuki|obiage|obi_jime|obi_makura|sode|obiita|pelvic_curtain|coattails|belt_buckle|o-ring|heart_o-ring|hip_vent|bow|ribbon|lace|sleeve_cuffs|detached_collar|stole', 'accessory')
add('corset|breast_curtains|single_breast_curtain|reverse_bunnysuit|reverse_bikini|bikini_top|crop_top|dougi|microdress|bodice', 'top')
add('bikini_bottom|cutoffs|loincloth|harem_pants|gaucho_pants', 'bottom')
add('petticoat|arm_warmers|uwabaki|okobo|geta|zori|wrist_guards|footwraps|tabi', 'accessory')
add('habit|kariginu|hagoromo|plugsuit|plugsuit_(evangelion)|chaldea_uniform|superhero_costume|military_uniform|military_dress_uniform|ainu_clothes|ancient_greek_clothes|aristocratic_clothes|meiji_schoolgirl_uniform|tactical_clothes|biker_clothes|tennis_uniform|workout_clothes|sleepwear|streetwear|arctic_clothes|cowboy_clothes|karategi|judogi|keikogi', 'outfit')
add('center_frills|double-breasted|breast_pocket|clothes_writing|blood_on_clothes|open_collar|button_gap|strap_gap|strap_slip|untied_bikini|untied_necktie|crotchless|crotchless_clothing|crotchless_panties|crotchless_bodysuit|crotchless_leotard|naked_ribbon|bra_visible_through_clothes|backboob|hip_cutout|pectoral_cleavage|wardrobe_malfunction|enmaided|crossdressing|unconventional_maid|wa_maid|wa_maid_outfit|male_swimwear|center_cutout|side_cutouts|straps|spikes|clothing_spikes|frayed_clothes|stained_clothes|burnt_clothes|faded_clothes|folded|unzipping|zipper_teeth', 'clothing.detail')
add('bikini_top_only', 'coverage', adult=True, excludes=('slot:bottom', 'slot:outfit', 'slot:underwear.bottom'))
add('bikini_bottom_only', 'coverage', adult=True, excludes=('slot:top', 'slot:outfit', 'slot:underwear.top'))
RULES[key('bikini_top_only')]['requires'] = ['top:bikini_top']
RULES[key('bikini_bottom_only')]['requires'] = ['bottom:bikini_bottom']
add('covering_privates|covering_crotch|covering_breasts|covering_nipples|covering_ass|covering_one_breast', 'hands.pose', adult=True)
add('hands_on_own_cheeks|hand_to_own_mouth|hand_over_own_mouth|steepled_fingers|shushing|trigger_discipline|v_over_eye|v_over_eyes|waking_up|cracking_knuckles|fist|raised_fist|raised_fists|open_hands|flat_hand|spread_fingers|crossed_fingers|finger_counting|finger_heart|finger_kiss|fingers_to_lips|hand_on_own_forehead|hand_on_own_nape|hands_on_own_nape|hand_behind_head|double_horns|horns_pose|rock_on|covering_own_ears|covering_own_eyes|covering_one_eye|covering_face|pointing|pointing_up|pointing_down|pointing_forward|arms_across_body|arms_between_legs|arms_on_knees|arm_on_knee|hand_between_own_legs|clenched_fist|clenched_fists|beckoning|making_a_fist|hand_sign|meditation|seiza|hanza', 'hands.pose')
add('leaning_to_the_side|top-down_bottom-up|presenting_armpit|one_knee|knee_bend|leg_raised|crossed_ankles|standing_on_tiptoes|leg_rest|leg_over_own_head|folded_body|flexible|planted|slouching', 'posture')
add('shivering|twitching|fidgeting|licking_lips|apologizing|bowing|curtsey|taunting|posing|shrug|shrugging|limbo|exercise|exercising|meditating|stretching_arms|stretching_legs|headbanging|tapping_foot|stomping|kicking|smelling|sniffing|praying|begging|singing|singing_into_microphone|saluting|looking_at_watch|heart_hands|blowing_bubble|blowing_bubbles', 'action')
add('pokemon_(creature)|digimon_(creature)|bug|machinery|skull|bone|bones|beachball|coin|flag|ofuda|cable|sign|drinking_straw|drinking_glass|remote_control|cushion|clipboard|whip|explosive|test_tube|pocket_watch|nintendo_switch|orb|stick|gourd|throne|kotatsu|locker|book_stack|ice_block|energy_sword|hose|scope|glowstick|christmas_ornaments|macaron|parfait|pancake|cake_slice|apple_slice|crayon|counter|concrete|condensation|condenser_unit|cork|flask|confetti|whistle|whisk|suction_cups|menu|medicine|mini-hakkero|millennium_puzzle|miracle_mallet|fishing_hook|fishing_line|fishing_bait|fishing_net|compass|compass_(instrument)|computer_keyboard|control_rod_(touhou)|model_kit|floating_object|familiar|shide|magatama|charm|amulet|talisman|vase|wrapping_paper|quill_pen|blood_bag|cigar|smoking_pipe|bandage_roll|bandage|shield|bayonet|stun_gun|tasers|taser|zapper|laser_gun|ray_gun|gadget|drone|missile_pod|portable_radio|stereo|boom_box|boombox|medicine_bottle|capsule|pill|pills|tablet_(medicine)|bottle_cap|laptop_bag|spray_bottle|ballpoint_pen|mechanical_pencil|stylus|calligraphy_brush|stuffed_animal|teddy_bear|raincoat|incense|incense_stick|incense_burner|electronic_board|motherboard|ramen_bowl|potted_plant', 'object')
add('pointer|pendulum|party_popper|pregnancy_test|riding_crop|scepter|sceptre|sketchbook|skewer|stethoscope|string|table_tennis_paddle|water_gun|watering_can|juice_box|fruit_cup|penlight_(glowstick)|sleeping_bag|toilet_paper|license_plate|stone_lantern|soul_gem|disco_ball|analog_clock|electric_plug|power_plug|acoustic_guitar|electric_guitar|bass_guitar|guitar_amplifier|amplifier|speaker|loudspeaker|speakers|microphone_stand|microwave|air_conditioner|air_conditioning_unit|washing_machine|vacuum_cleaner|wheel|wheelbarrow|winch|cogwheel|rubber_band|bendy_straw|crazy_straw|heart_straw|ice_crystal|snow_globe|crystal_ball|fortune_cookie|rice_cracker|pie_slice|pizza_slice|orange_slice|lemon_slice|lime_slice|bread_slice|cucumber_slice|watermelon_slice|strawberry_slice|pear_slice|peach_slice|banana_slice|pineapple_slice|tomato_slice|potato_slice|mushroom_slice|sweet_potato|potato_chips|french_fries|chewing_gum|gumball|gumballs|candy_cane|candy_apple|candied_apple|marshmallow|cotton_candy|sugar_cube|tea_bag|coffee_beans|tea_leaves|rice_ball|rice_bowl|soup_bowl|salad_bowl|honey_jar|jam_jar|cookie_jar|milk_bottle|wine_glass|cocktail_glass|champagne_flute|shot_glass|beer_mug|drinking_cup|plastic_cup|paper_cup|glass_cup|glass_bottle|plastic_bottle|pitcher_(container)|jug|jug_(bottle)|water_bottle|sports_bottle|water_flask|vending_machine|coin_op|slot_machine|arcade_cabinet|crane_game|playstation_portable|game_boy|game_boy_advance|nintendo_ds|nintendo_3ds|nintendo_wii|steam_deck|playstation|xbox|playstation_controller|dualshock|nintendo_switch_controller|joy-con|console|handheld_game_console|plastic_box|wooden_box|metal_box|cardboard_box|shipping_container|storage_box|toolbox|jewelry_box|lunchbox|music_box|toy_box|folding_fan|hand_fan|globe|terrestrial_globe|planetarium|telescope|periscope|binoculars|magnifier|surgical_mask|oxygen_mask|eyewear|handheld_radio|walkie-talkie|walkman|cassette_tape|compact_disc|vinyl_record|record_player|tape_recorder|digital_clock|alarm_clock|wristwatch|stopwatch|sundial|hourglass|astrolabe|photo_(object)|photograph_(object)|furniture|ribbon_spool|thread_spool|yarn_ball|knitting_needles|sewing_needle|sewing_machine|sewing_kit|pin|pushpin|thumbtack|safety_pin|clothespin|hair_clipper|clippers|nail_clippers|tweezers|razor|shaving_razor|razor_blade|fountain_pen|dip_pen|paint_tube|paint_can|paint_bucket|paint_roller|paint_palette|artist_palette|easel|drawing_tablet|graphics_tablet|tablet_computer|paper_stack|pile_of_books|plate_stack|stack_of_plates|bookcase|shelf|nightstand|coat_rack|hat_stand|umbrella_stand|futon|mattress|comforter|duvet|bed_sheet|pillowcase|seat_cushion|floor_cushion|zabuton|rocking_chair|folding_chair|bean_bag_chair|deck_chair|lounge_chair|beach_chair|folding_table|coffee_table|dining_table|dining_chair|picnic_table|picnic_basket|picnic_blanket|basketball|volleyball|soccer_ball|football|baseball_(object)|baseball_bat|baseball_glove|tennis_ball|tennis_racket|badminton_racket|shuttlecock|ping_pong_ball|table_tennis_ball|bowling_ball|bowling_pin|golf_ball|golf_club|hockey_stick|hockey_puck|rugby_ball|dumbbell|barbell|weight_plate|kettlebell|jump_rope|skipping_rope|resistance_band|exercise_ball|yoga_mat|exercise_mat|fishing_basket|fishing_reel|fish_hook|fishing_tackle|bait|fishing_lure|hook|sink|shower_head|bathtub|washbasin|basin|bucket|garden_hose|water_hose|fire_hose|fire_extinguisher|traffic_sign|stop_sign|road_sign|traffic_light|street_sign|mailbox|letter_box|post_box|trash_can|garbage_can|wastebasket|recycling_bin|dumpster|aircraft|antique_firearm|kalashnikov_rifle|rocket_launcher|grenade_launcher|flamethrower|battle_axe|battleaxe|warhammer|maul|flail|morning_star|spiked_club|club_(weapon)|baton|tonfa|nunchaku|bo_staff|quarterstaff|pole|wooden_sword|bokken|training_sword|rubber_duck|rubber_ducky|piggy_bank|keychain|key_ring|key_holder|bottle_opener|corkscrew|can_opener|handcuff_key|door_key|car_key|padlock_key|bell|handbell|cowbell|wind_chime|dreamcatcher|fly_swatter|bug_net|insect_net|butterfly_net|spade|trowel|pitchfork|rake|hoe|plow|plough|sickle|scythe|watering_hose|fan_(object)|electric_fan|portable_fan|paper_fan|mask_(object)|venus_flytrap|succulent|cactus|bonsai|fern|ivy|vine|creeper|mint_(plant)|holly|mistletoe|rose_bush|moss|lichen|coral|coral_reef', 'object')
add('bear|polar_bear|brown_bear|black_bear|panda|red_panda|chick|duck|seagull|pigeon|crane|swan|goose|penguin|parrot|macaw|cockatoo|finch|swallow|sparrow|canary|hummingbird|owl|eagle|hawk|falcon|vulture|condor|dragonfly|damselfly|firefly|cicada|cricket|grasshopper|mantis|ladybug|ladybird|beetle|ant|bee|wasp|hornet|butterfly|moth|cockroach|spider|scorpion|centipede|millipede|caterpillar|earthworm|leech|snail|slug|slugs|slime_mold|turtle|tortoise|lizard|gecko|iguana|chameleon|snake|cobra|python|frog|toad|salamander|newt|axolotl|fish|tropical_fish|flying_fish|goldfish|pufferfish|sunfish|catfish|carp|koi|shark|stingray|seahorse|dolphin|orca|whale|jellyfish|octopus|squid|cuttlefish|starfish|urchin|sea_urchin|crab|lobster|shrimp|prawn|crayfish|coral|clam|oyster|scallop|mussel|pig|boar|cow|bull|calf|sheep|ram|goat|deer|elk|moose|reindeer|horse|pony|donkey|mule|yak|bison|buffalo|camel|dromedary|llama|alpaca|raccoon|tanuki|badger|weasel|otter|ferret|stoat|mink|skunk|fox|wolf|jackal|coyote|hyena|lion|tiger|panther|jaguar|leopard|cheetah|lynx|bobcat|cougar|puma|snow_leopard|elephant|rhinoceros|hippopotamus|giraffe|zebra|gazelle|antelope|monkey|ape|gorilla|orangutan|chimpanzee|gibbon|baboon|lemur|sloth|anteater|armadillo|pangolin|squirrel|chipmunk|beaver|groundhog|marmot|capybara|chinchilla|mouse|rat|hamster|gerbil|guinea_pig|rabbit|hare|hedgehog|porcupine|bat_(animal)|seal|sea_lion|walrus|platypus|koala|kangaroo|wallaby|wombat|possum|opossum|dinosaur|tyrannosaurus|velociraptor|triceratops|pterosaur|pterodactyl|mammoth|saber-toothed_tiger|smilodon|phoenix|griffin|gryphon|wyvern|unicorn|pegasus|chocobo|pikmin_(creature)', 'object')
# Portable hand tools and implements. Each is a concrete, held object per its own
# Wiki definition ("a hooked or curved steel bar used as a tool", "a small
# hand-held object", "an object with a broad blade attached to a handle"), which
# is what lets the holding_<name> gesture resolve to an owned prop.
add('crowbar|drumsticks|lighter|mop|notepad|paddle|toothbrush', 'object')
add('brothel|poolside|doorway|bar_(place)|onsen|stage|auditorium|concert_hall|dining_room|living_room|restroom|washroom|waterfront|city_square|waterpark|mountain_path|space_station|outdoor_cafe|cafe_terrace|school|school_interior|dormitory|castle|ruined_castle|ruined_building|abandoned_building|aquarium|arcade|apartment|bath|bathroom|moon_(place)|arena|dojo|fire_escape|basement|attic|loft|factory|workshop|train_platform|train_car|railway_platform|airport|airplane_interior|airship|hot_springs|shrine|shrine_grounds|camp|campsite|field|nightclub|bridge|beach', 'location')
add('breath|puff_of_air|aura|electricity|magic|energy|city_lights|stage_lights|magic_circle|hitodama|power_lines|utility_pole|spider_web|roots|debris|reflective_liquid|paint_splatter|paint_splashes|floating_particles|dust_motes|constellation|shooting_star|shooting_stars|earth_(planet)|milky_way|shooting_star|ceiling|puddle|snowdrift|rain_drops|snow_crystal|rainwater|hail|heat_haze|flame|flames|firefly|light_beam|laser_beam|lightning_bolt|sparks|embers|blood_splatter|splatter|scaffolding|scaffolding|paper_lantern|paper_lanterns|straw_bale|haystack|bamboo_forest|flower_field|fields|architecture|east_asian_architecture|landscape|scenery|still_life', 'scene.detail')
add('christmas|halloween|new_year|valentine|valentine_day|valentines_day|april_fools|anniversary|birthday|milestone_celebration|announcement_celebration|ancient_egyptian|ancient_greek|medieval|winter|summer|autumn|spring|cowboy_western|slice_of_life|science_fiction|fantasy|horror_(theme)|sports|sport|country_theme|historic|historical', 'style')
add('style_parody|art_parody|artist_self-insert|one-hour_drawing_challenge|doujin_cover|chromatic_aberration|film_grain|noise|noisy_image|fake_screenshot|hatching_(texture)|painterly|surreal|surrealism|glitch|glitch_art|afterimage|x-ray|cross-section|bad_anatomy|artistic_error|scribble|scenery|still_life|abstract|abstract_art|abstraction|non-representational|pixelated|pixelation|pixel_(medium)|watercolor|watercolour|wash|ink_wash|splatter_art|charcoal|graphite|sepia|fisheye|perspective|pillarboxed|letterboxed|color_contrast|warm-cool_contrast|complementary_colors|contrast|symmetry|asymmetry|bilateral_symmetry|render|flat_color|flat_coloring|unshaded|smooth_shading|rough_shading|rough_lines|crosshatching|screen_tone|screentone|ben-day_dots|halftone|halftone_dots|gradient_map|drawing_(medium)|photograph_(medium)|photograph|duotone|tritone', 'style')
add('barcode|pentagram|mitsudomoe_(shape)|ankh|latin_cross|nordic_cross|squeans|arrow_through_heart|starburst|question_mark|exclamation_mark|double_exclamation_mark|heart|hearts|circle|spiral|triangle|square|hexagon|geometry|notice_line|anger_vein|anger_symbol|sweatdrop_symbol|impact_star|impact_lines', 'symbol')
add('page_number|brand_name|patreon_username|weibo_username|weibo_watermark|artist_name|song_name|romaji_text|song_title|thank_you|happy_birthday|happy_new_year|merry_christmas|congratulations|web_address|content_rating|rating_label|speech|text_bubble|spoken_heart|spoken_character|spoken_question_mark|spoken_exclamation_mark|spoken_ellipsis|onomatopoeia|thought_bubble|text_message|english_text|japanese_text|chinese_text|korean_text|russian_text|spanish_text|french_text|german_text|italian_text|arabic_text|hebrew_text|thai_text|portuguese_text|indonesian_text|vietnamese_text|numbered|countdown|date|title|subtitle|copyright_notice|copyright_name|signature|watermark|numerals|roman_numerals', 'text')
for color in 'aqua black blue brown green grey orange pink purple red white yellow silver gold beige'.split():
    add(color + '_theme', 'style', phrase='a predominantly ' + color + ' color palette')
    RULES[key(color + '_theme')]['features'] = {'image.palette': color}
for decade in range(1950, 2020, 10):
    add(str(decade) + 's_(style)', 'style', phrase='the visual style of the ' + str(decade) + 's')
for name in ('bad_anatomy', 'artistic_error', 'drawing_error', 'human_error'):
    if key(name) in RULES:
        RULES[key(name)]['conditions'] = ['ordinary_only']
for name in ('zettai_ryouiki', 'pantyshot', 'panties_under_pantyhose', 'bra_visible_through_clothes'):
    add(name, 'clothing.exposure', adult=True)
for name in ('uncensored', 'decensored', 'out-of-frame_censoring', 'pointless_censoring', 'novelty_censor', 'censored', 'mosaic_censoring', 'bar_censor', 'convenient_censoring', 'light_censor', 'steam_censor', 'blur_censor'):
    add(name, 'style', adult=True)
RULES[key('uncensored')]['features'] = {'image.censorship': 'none'}
for name, rule in RULES.items():
    if 'censor' in name and name not in {'uncensored', 'decensored'}:
        rule['features'] = {'image.censorship': 'present'}

add('office_lady|ninja|knight|sailor|nun|police|police_officer|policewoman|policeman|waitress|waiter|teacher|student|schoolgirl|schoolboy|dancer|idol|idol_singer|race_queen|bride|groom|chef|cook|baker|barista|bartender|butler|maid|waitstaff|doctor|nurse|surgeon|soldier|military_operator|pilot|fighter_pilot|astronaut|scientist|researcher|mechanic|engineer|technician|librarian|secretary|receptionist|banker|businessman|businesswoman|accountant|firefighter|lifeguard|guard|security_guard|priest|priestess|miko|shrine_maiden|monk|bishop|pope|king|queen|prince|princess|noble|nobleman|noblewoman|emperor|empress|royalty|aristocrat|pirate|cowboy|cowgirl_(western)|samurai|ronin|warrior|swordsman|swordswoman|fencer|archer|hunter|ranger|mercenary|adventurer|paladin|mage|magician|witch|wizard|sorcerer|sorceress|necromancer|druid|cleric|demon_hunter|monster_hunter|martial_artist|fighter|wrestler|boxer|sumo_wrestler|athlete|swimmer|tennis_player|baseball_player|basketball_player|soccer_player|football_player|volleyball_player|golfer|gymnast|figure_skater|cheerleader|musician|conductor|violinist|guitarist|pianist|singer|rocker|rock_star|punk_rocker|model|fashion_model|artist|painter|illustrator|writer|author|poet|photographer|reporter|journalist|detective|investigator|lawyer|judge|merchant|shopkeeper|farmer|fisherman|fisherwoman|gardener|florist|carpenter|blacksmith|miner|lumberjack|courier|delivery_person|deliveryman|delivery_girl|postal_worker|train_conductor|bus_driver|taxi_driver|race_car_driver|truck_driver|racer|biker|motorcyclist|performer|actor|actress|comedian|clown|jester|acrobat|magical_girl|magical_boy|superhero|superheroine|supervillain|villain|villainess|hero|heroine|delinquent|sukeban|bancho|tomboy|gyaru|kogal|otaku|goth|hippie|gangster|yakuza|mobster|thief|rogue|assassin|spy|agent|magical_nurse|angel_of_death', 'body.role')
for name, rule in RULES.items():
    if rule['slot'] == 'body.role':
        from app.prompts.semantic_scene import article
        rule['phrase'] = 'the role or appearance of ' + article(name)
        rule['conditions'] = ['original_only']
        if name in {'magical girl', 'magical boy', 'schoolgirl', 'schoolboy', 'kogal', 'delinquent', 'sukeban', 'bancho'}:
            rule['conditions'].append('ordinary_only')
        if name in {'office lady', 'policewoman', 'waitress', 'nun', 'bride', 'cowgirl (western)', 'schoolgirl', 'magical girl', 'shrine maiden', 'miko', 'princess', 'queen', 'empress', 'sorceress', 'actress', 'businesswoman', 'noblewoman', 'swordswoman', 'superheroine', 'villainess', 'heroine', 'race queen'}:
            rule['conditions'].append('gender:female')
        elif name in {'policeman', 'waiter', 'groom', 'cowboy', 'schoolboy', 'magical boy', 'prince', 'king', 'emperor', 'businessman', 'nobleman', 'swordsman', 'fisherman'}:
            rule['conditions'].append('gender:male')
add('furry|furry_female|furry_male|monster_girl|monster_boy|demon|demon_girl|demon_boy|angel|ghost|android|cyborg|vampire|oni|jiangshi|nekomata|kitsune|dark_elf|alien|giant|giantess|merfolk|mermaid|merman|lamia|arachne|harpy|taur|centaur|minotaur|draph|erune|miqo\'te|mithra_(ff11)|au_ra|viera|hyur|elezen|roegadyn|hrothgar|lalafell|inkling|octoling|mecha_musume|kemonomimi|humanization|anthropomorphism|personification', 'body.species')
for name, rule in RULES.items():
    if rule['slot'] == 'body.species':
        rule['conditions'] = ['original_only']
        if name.endswith((' girl', ' female', 'giantess')) or name in {'mermaid', 'mecha musume'}:
            rule['conditions'].append('gender:female')
        if name.endswith((' boy', ' male')) or name == 'merman':
            rule['conditions'].append('gender:male')
        rule['features'] = {'body.species': name}
        if name in {'merfolk', 'mermaid', 'merman', 'lamia', 'arachne', 'centaur', 'taur'}:
            rule['excludes'] = ['slot:footwear', 'slot:legwear', 'action:walking', 'action:running']
add('virtual_youtuber|vtuber|androgynous|bishounen|mature_female|mature_male|manly|tomboy|petite|mini_person|minigirl|miniboy|fat_man|old|old_man|one-eyed|faceless|faceless_female|faceless_male|feminine_male|masculine_female|tall_female|tall_male|short_female|short_male|young_adult|middle-aged|middle-aged_female|middle-aged_male', 'body.shape')
for name in ('child', 'baby', 'toddler', 'young', 'young_girl', 'young_boy', 'chibi_only'):
    add(name, 'body.shape' if name != 'chibi_only' else 'style')
    RULES[key(name)]['conditions'] = ['ordinary_only', 'original_only']
for name in ('futanari', 'male_masturbation', 'female_masturbation', 'masturbation'):
    add(name, 'body.detail' if name == 'futanari' else 'action', adult=True)
    RULES[key(name)]['conditions'] = ['original_only']
    if name != 'futanari':
        RULES[key(name)]['phrase'] = 'masturbating'
RULES['futanari']['conditions'].append('gender:female')
for name in ('no_shoes', 'no_socks', 'no_shirt', 'no_bra', 'no_panties', 'no_underwear'):
    add(name, 'clothing.detail', adult=name in {'no_bra', 'no_panties', 'no_underwear'})
RULES['no shoes']['excludes'] = ['slot:footwear']
RULES['no shoes']['required_slots'] = [['legwear']]
RULES['no shirt']['excludes'] = ['slot:top']
RULES['no shirt']['adult'] = True
RULES['no socks']['excludes'] = ['slot:legwear']
for name, slot in (('no bra', 'underwear.top'), ('no panties', 'underwear.bottom'), ('no underwear', 'underwear')):
    RULES[name]['excludes'] = ['slot:' + slot]

RELATIONS = {
    'couple': ('{0} and {1} are a romantic couple', (), False, False),
    'hetero': ('{0} and {1} share a romantic interaction', ('male', 'female'), False, False),
    'yuri': ('{0} and {1} share a romantic interaction', ('female', 'female'), False, False),
    'yaoi': ('{0} and {1} share a romantic interaction', ('male', 'male'), False, False),
    'siblings': ('{0} and {1} are siblings', (), False, True),
    'sisters': ('{0} and {1} are sisters', ('female', 'female'), False, True),
    'brothers': ('{0} and {1} are brothers', ('male', 'male'), False, True),
    'brother and sister': ('{0} is the brother of {1}', ('male', 'female'), False, True),
    'twins': ('{0} and {1} are twins', (), False, True),
    'cousins': ('{0} and {1} are cousins', (), False, True),
    'husband and wife': ('{0} and {1} are husband and wife', ('male', 'female'), False, True),
    'confession': ('{0} confesses romantic feelings to {1}', (), False, False),
    'marriage proposal': ('{0} proposes marriage to {1}', (), False, False),
    'arguing': ('{0} and {1} are arguing with each other', (), False, False),
    'confrontation': ('{0} and {1} face each other in a confrontation', (), False, False),
    'heads together': ('{0} and {1} have their heads together', (), False, False),
    'behind another': ('{0} is positioned behind {1}', (), False, False),
    'side-by-side': ('{0} and {1} are positioned side by side', (), False, False),
    'carrying person': ('{0} carries {1}', (), False, False),
    'lifting person': ('{0} lifts {1}', (), False, False),
    'leaning on person': ('{0} leans on {1}', (), False, False),
    'lying on person': ('{0} lies on {1}', (), False, False),
    'girl on top': ('{0} is positioned above {1}', ('female', 'any'), False, False),
    'boy on top': ('{0} is positioned above {1}', ('male', 'any'), False, False),
    'hug from behind': ('{0} hugs {1} from behind', (), False, False),
    'grabbing from behind': ('{0} grasps {1} from behind', (), False, False),
    'covering with blanket': ('{0} covers {1} with a blanket', (), False, False),
    'feeding': ('{0} feeds {1}', (), False, False),
    'fighting': ('{0} and {1} are fighting each other', (), False, False),
    'punching': ('{0} punches toward {1}', (), False, False),
    'poking': ('{0} pokes {1}', (), False, False),
    'chasing': ('{0} chases {1}', (), False, False),
    'french kiss': ('{0} and {1} share a French kiss', (), True, False),
    'groping': ('{0} sexually caresses {1}', (), True, False),
}
for name, (phrase, genders, adult, original) in RELATIONS.items():
    RULES[name] = primitive(name, 'interaction', actors=2, adult=adult)
    RULES[name]['role_phrase'] = phrase
    RULES[name]['role_genders'] = genders
    if original:
        RULES[name]['conditions'] = ['original_only']
RULES['covering with blanket']['role_requires'] = [['object:blanket'], []]
RULES['feeding']['role_requires'] = [['object:food'], []]
RULES['lying on person']['role_requires'] = [['posture:lying'], []]
RULES['crossover'] = primitive('crossover', 'interaction', actors=2, phrase='meeting across different franchises')
RULES['crossover']['conditions'] = ['different_copyrights']
RULES['no humans'] = primitive('no humans', 'scene.detail', phrase='no human or humanoid characters')
RULES['no humans']['conditions'] = ['creature_only']
for name, gender in (('multiple girls', 'female'), ('multiple boys', 'male')):
    RULES[name] = primitive(name, 'count', phrase='at least two ' + gender + ' subjects', actors=2)
    RULES[name]['conditions'] = [gender + ':2']


ACTIVITIES = {
    'taking picture': ('taking a photograph', ('camera',), ()),
    'mirror selfie': ('taking a selfie in front of a mirror', ('smartphone', 'mirror'), ()),
    'archery': ('drawing and aiming a bow', ('bow (weapon)', 'arrow (projectile)'), ()),
    'typing': ('typing on a keyboard', ('computer keyboard',), ()),
    'knitting': ('knitting with yarn and knitting needles', ('yarn', 'knitting needles'), ()),
    'sewing': ('sewing fabric with a needle', ('sewing needle', 'cloth'), ()),
    'embroidering': ('embroidering fabric', ('sewing needle', 'cloth'), ()),
    'ironing': ('ironing clothing', ('iron',), ()),
    'skateboarding': ('riding a skateboard', ('skateboard',), ('posture:standing',)),
    'surfing': ('surfing on a surfboard', ('surfboard',), ('scene.detail:water',)),
    'sweeping': ('sweeping with a broom', ('broom',), ()),
    'mopping': ('mopping the floor', ('mop',), ('scene.detail:floor',)),
    'vacuuming': ('using a vacuum cleaner', ('vacuum cleaner',), ()),
    'watering plants': ('watering plants with a watering can', ('watering can',), ('scene.detail:plant',)),
    'gardening': ('gardening with a trowel', ('trowel',), ('scene.detail:plant',)),
    'firing': ('firing a gun', ('gun',), ()),
    'aiming': ('aiming a weapon', ('weapon',), ()),
    'aiming at viewer': ('aiming a weapon toward the viewer', ('weapon',), ()),
    'broom riding': ('riding a flying broom', ('broom',), ()),
    'playing games': ('playing a video game', ('game controller',), ()),
    'playing guitar': ('playing a guitar', ('guitar',), ()),
    'playing piano': ('playing a piano', ('piano',), ()),
    'playing violin': ('playing a violin', ('violin',), ()),
    'playing flute': ('playing a flute', ('flute',), ()),
    'singing into microphone': ('singing into a microphone', ('microphone',), ()),
    'brushing teeth': ('brushing their teeth', ('toothbrush',), ()),
    'drying hair': ('drying their hair with a hair dryer', ('hair dryer',), ()),
    'blowing bubbles': ('blowing soap bubbles', ('bubble wand',), ()),
}


def supplemental_rule(name, page, lookup):
    normalized = key(name)
    raw = definition(page.get('body', ''))
    text = plain(raw)
    if not text or UNRESOLVED.search(text) or UNRESOLVED.search(normalized):
        return None, None
    rule = None
    family = ''
    if normalized in RULES:
        rule = {**RULES[normalized]}
        rule['adult'] = rule['adult'] or bool(ADULT.search(normalized))
        family = 'specific_visual_concept'
        if rule['slot'].startswith('clothing.') and not normalized.startswith('no '):
            rule['required_slots'] = [list(APPAREL)]
    if normalized in ACTIVITIES:
        phrase, props, facts = ACTIVITIES[normalized]
        required = [lookup(prop) for prop in props]
        if all(required):
            rule = primitive(name, 'action', phrase=phrase, requires=tuple('object:' + key(prop) for prop in props) + facts)
            family = 'specific_action_dependencies'
    # Ordinary self-placement poses carry no inferred relationship to another
    # subject. A named table or pillow is an actual prerequisite object.
    if rule is None and (match := re.fullmatch(r'(hand|hands|arm|arms|elbow|elbows|head|chin|foot|feet|leg|legs) (on|under|over|between|behind) (?:own )?(' + PARTS + r'|table|desk|pillow|headwear)', normalized)):
        limb, prep, target = match.groups()
        if not re.search(r"\b(?:another|someone else|other character|person's)\b", text[:350], re.I):
            rule = primitive(name, 'hands.pose' if limb in {'hand', 'hands', 'arm', 'arms', 'elbow', 'elbows'} else 'legs.pose' if limb in {'foot', 'feet', 'leg', 'legs'} else 'posture',
                phrase=f'{limb} {prep} ' + ('their own ' if target not in {'table', 'desk', 'pillow', 'headwear'} else 'a ') + target,
                adult=bool(ADULT.search(target) or target in {'breast', 'breasts', 'ass', 'buttocks', 'crotch'}))
            if target in {'table', 'desk', 'pillow'}:
                rule['requires'] = ['object:' + target]
            if target == 'headwear':
                rule['required_slots'] = [['headwear']]
            family = 'self_pose_geometry'
    if rule is None and (match := re.fullmatch(r'(arm|arms|hand|hands|head|heads|chin|leg|legs|foot|feet) (on|around|behind|under|over|between|against) (?:another\'s )?(' + PARTS + ')', normalized)):
        limb, prep, target = match.groups()
        if re.search(r'\b(?:another|other|someone|one character|one person)\b', text[:350], re.I):
            rule = primitive(name, 'interaction', actors=2, adult=bool(ADULT.search(target) or target in {'breast', 'breasts', 'ass', 'buttocks', 'crotch'}))
            rule['role_phrase'] = '{0} rests ' + ('both ' if limb.endswith('s') else 'an ' if limb == 'arm' else 'a ') + limb + ' ' + prep + " {1}'s " + target
            family = 'ordered_pose_geometry'
    if rule is None and (match := re.fullmatch(r'(?:adjusting|brushing|combing|tying|braiding|stroking|playing with|covering|pinching|poking|patting|licking|biting|kissing|sucking|massaging|washing|cleaning|drying) another\'s (' + PARTS + r'|clothes|clothing|makeup)', normalized)):
        target = match[1]
        verb = normalized.split(" another's", 1)[0]
        finite = {'adjusting': 'adjusts', 'brushing': 'brushes', 'combing': 'combs', 'tying': 'ties', 'braiding': 'braids', 'stroking': 'strokes', 'playing with': 'plays with', 'covering': 'covers', 'pinching': 'pinches', 'poking': 'pokes', 'patting': 'pats', 'licking': 'licks', 'biting': 'bites', 'kissing': 'kisses', 'sucking': 'sucks', 'massaging': 'massages', 'washing': 'washes', 'cleaning': 'cleans', 'drying': 'dries'}[verb]
        rule = primitive(name, 'interaction', actors=2, adult=bool(ADULT.search(target) or target in {'breast', 'breasts', 'ass', 'buttocks', 'crotch'}))
        rule['role_phrase'] = '{0} ' + finite + " {1}'s " + target
        if verb in {'brushing', 'combing'}:
            prop = 'hair brush' if verb == 'brushing' else 'comb'
            if not lookup(prop):
                return None, None
            rule['role_requires'] = [['object:' + prop], []]
        family = 'ordered_grooming_action'
    if rule:
        return rule, {'family': family, 'definition': text[:600], 'passage': raw[:900]}
    return None, None
