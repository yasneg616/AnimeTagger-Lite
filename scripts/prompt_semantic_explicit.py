"""Reviewed attribute/gesture grammars and their structural requirements."""
from __future__ import annotations

import re

from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_rules import primitive
from scripts.prompt_semantic_families import ADULT, definition, plain


EXPLICIT = {}


def register(names, slot, *, phrase=None, requires=(), excludes=(), provides=(), features=None, adult=False, actors=1):
    for name in names.split("|"):
        rule = primitive(name, slot, phrase=phrase, requires=requires, excludes=excludes,
                         provides=provides, adult=adult, actors=actors)
        if features:
            rule["features"] = dict(features)
        EXPLICIT[key(name)] = rule


# These definitions describe an interface, artifact or outline, rather than the
# place nouns that happen to occur in their names or introductory prose.
register('health_bar', 'symbol', phrase='a video-game health meter')
register('chocolate_bar', 'object', phrase='a bar of chocolate')
register("bishamonten's_pagoda", 'object', phrase="Bishamonten's miniature jeweled pagoda")
register('negative_space', 'framing', phrase='deliberate empty space around the subjects')
register('pool_ladder', 'object', phrase='a swimming-pool ladder')
register('sand_castle', 'scene.detail', phrase='a sand castle')
register('skyline', 'scene.detail', phrase='a city skyline')
register('spreader_bar', 'object', phrase='a spreader bar', adult=True)
register('bespectacled', 'eyes.detail', phrase='wearing glasses as a change from their usual appearance', requires=('accessory:glasses',))


# Source definitions identify these physical entities by function or material.
# Their type does not depend on a matching noun mentioned in a later example.
register('animal|anti-aircraft_gun|artillery|binder|bird|cabinet|cane|canvas_(object)|card|chalk|chicken|corn|couch|cream|drugs|egg|fireworks|folding_screen|fruit_as_cup|gohei|googly_eyes|grenade|iv_stand|jingle_bell|locomotive|magazine_(object)|magnifying_glass|mimic_chest|monster|net|oil_lamp|pastry|picture_frame|qingxin_flower|sauce|sausage|steak|super_mushroom|tape|tape_measure|toilet|toothpaste|train|trash|urinal|wind_turbine|wire|watercraft|gold|charm_(object)', 'object')
register('badge|blindfold|cuffs|fur-trimmed_collar|legwear_garter|monocle|sarashi', 'accessory')
register('bib', 'accessory')
EXPLICIT[key('bib')]['conditions'] = ['ordinary_only']
EXPLICIT[key('blindfold')]['features'] = {'eyes.state': 'obscured'}
EXPLICIT[key('blindfold')]['excludes'] = ['slot:gaze']
register('pasties', 'accessory', adult=True)
register('bandeau', 'underwear.top', adult=True)
register('fundoshi|g-string|thong', 'underwear.bottom', adult=True)
register('flight_suit|otonokizaka_school_uniform|sakugawa_school_uniform', 'outfit')
register('mizu_happi', 'outfit', adult=True)
register('antennae', 'body.detail', phrase='antennae on the head')
EXPLICIT[key('antennae')]['conditions'] = ['original_only']
register('beard_stubble|forehead|lips|hand_blush|facepaint|tanlines|belly|tacet_mark_(wuthering_waves)', 'body.detail')
EXPLICIT[key('forehead')]['phrase'] = 'a prominently visible forehead'
EXPLICIT[key('belly')]['phrase'] = 'a slightly rounded belly'
register('lips', 'face.detail', phrase='noticeably visible lips')
register('double_halo', 'body.halo', phrase='two halos')
EXPLICIT[key('double_halo')]['features'] = {'body.halo.count': '2'}
register('multiple_braids', 'hair.style', phrase='three or more braids', excludes=('hair.length:bald',))
register('brick|caterpillar_tracks|column|nebula|pillar|planet|waves', 'scene.detail')
register('artist_logo|power_symbol|paw_print|chinese_zodiac', 'symbol')
register('blue_border', 'border', phrase='a blue border')
register('leaf_background', 'background', phrase='a background featuring leaves')
register('meme', 'style', phrase='an internet meme composition')
register('wrestling_ring', 'location', phrase='a professional wrestling ring')
register('finger_frame', 'hands.pose', phrase='forming a rectangular frame with the fingers')
register('fox_shadow_puppet', 'hands.pose', phrase='forming a fox-shaped shadow puppet with a hand')
register('rubbing_eyes', 'action', phrase='rubbing their eyes')
EXPLICIT[key('rubbing_eyes')]['features'] = {'eyes.state': 'closed', 'body.eyes.present': 'yes'}
register(';o', 'expression', phrase='a wink with a round open mouth', requires=('mouth:open_mouth',))
register('hat_ribbon', 'clothing.trim', phrase='a ribbon tied around the hat')
EXPLICIT[key('hat_ribbon')]['required_slots'] = [['headwear']]
register('shoe_soles', 'clothing.detail', phrase='visible soles of the footwear')
EXPLICIT[key('shoe_soles')]['required_slots'] = [['footwear']]
register('no_pants', 'coverage', phrase='wearing a top and underwear without outer bottoms', adult=True,
         excludes=('slot:bottom', 'slot:outfit'))
EXPLICIT[key('no_pants')]['required_slots'] = [['top'], ['underwear.bottom']]
register('lap_pillow', 'interaction', actors=2)
EXPLICIT[key('lap_pillow')]['role_phrase'] = "{0} rests their head in {1}'s lap"
EXPLICIT[key('lap_pillow')]['role_requires'] = [['posture:lying'], ['posture:sitting']]
register('rock_paper_scissors', 'interaction', actors=2, phrase='playing rock-paper-scissors together')


# Attribute lengths and widths occupy different dimensions. Their existence is
# established by a worn garment or explicit detached sleeves at compile time.
for name, length in (("long_sleeves", "long"), ("short_sleeves", "short"),
                     ("sleeveless", "none"), ("three-quarter_sleeves", "three-quarter"),
                     ("sleeves_past_wrists", "long"), ("sleeves_past_fingers", "long")):
    register(name, "clothing.sleeves", features={"clothing.sleeves.length": length})
register("puffy_sleeves|puffy_short_sleeves|puffy_long_sleeves|juliet_sleeves", "clothing.sleeves", features={"clothing.sleeves.shape": "puffy"})
EXPLICIT[key("puffy_short_sleeves")]["features"]["clothing.sleeves.length"] = "short"
EXPLICIT[key("puffy_long_sleeves")]["features"]["clothing.sleeves.length"] = "long"
register("wide_sleeves", "clothing.sleeves", features={"clothing.sleeves.opening": "wide"})
register("short_over_long_sleeves", "clothing.sleeves", phrase="short sleeves layered over long sleeves", provides=("layered_sleeves",))
register("detached_sleeves|frilled_sleeves|ribbon-trimmed_sleeves|fur-trimmed_sleeves|lace-trimmed_sleeves|sleeves_rolled_up|single_sleeve|asymmetrical_sleeves|sleeve_cuffs|detached_cuffs|flared_sleeves|tight_sleeves|bell_sleeves|split_sleeves|layered_sleeves", "clothing.sleeves")
register("sailor_collar|wing_collar|high_collar|standing_collar|frilled_collar|shirt_collar|frilled_shirt_collar|lace-trimmed_collar|fur_collar|peter_pan_collar|detached_collar|collared|cowl_neck|plunging_neckline|low_neckline|scoop_neck|v-neck|crew_neck|jabot", "clothing.collar")
register("frills|fur_trim|lace_trim|ribbon_trim|gold_trim|silver_trim|colorful_trim|neon_trim|piping|bias_tape|tassel|tassels|pom_pom_(clothes)|ruffles|ruffle|pleats|buttons|buckle|buckles|zippers|zipper|pockets|pocket|decorative_button|diamond_button|heart_button|star_button|cross_button|flower_button|frog_button|anchor_button|epaulettes", "clothing.trim")
register("denim|leather|latex|rubber|silk|satin|velvet|wool|knit|knitted|ribbed|cable_knit|fishnets|lace|mesh|spandex|spandex_clothes|fur|sequins|sequin|metallic_clothes|feather-trimmed_clothes", "clothing.material")
register("striped_clothes|plaid_clothes|checkered_clothes|polka_dot|floral_print|animal_print|vertical-striped_clothes|horizontal-striped_clothes|diagonal-striped_clothes|pinstriped_clothes|argyle_clothes|herringbone|gingham|gingham_check|gingham_clothes|camouflage_clothes|geometric_pattern|paisley|houndstooth|floral_pattern", "clothing.pattern")
register("open_clothes|unbuttoned|partially_unbuttoned|unzipped|partially_unzipped|open_fly|open_shirt|open_jacket|open_coat|open_vest|torn_clothes|ripped_clothes|dirty_clothes|wet_clothes|partially_removed_clothes|clothing_cutout|side_slit|side_cutout|back_cutout|shoulder_cutout|navel_cutout|chest_cutout|cleavage_cutout|above-cleavage_cutout|underboob_cutout|pelvic_cutout|heart_cutout|center_opening|off_shoulder|single_bare_shoulder|off-shoulder|strapless|halterneck|highleg|lowleg|two-sided_fabric|revealing_clothes|midriff_peek|underbust|criss-cross_halter|crotch_seam|backless_outfit", "clothing.exposure")
register("see-through|see-through_clothes|transparent_clothes|see-through_sleeves|see-through_cleavage|nipple_slip|underwear_only", "clothing.exposure", adult=True)
register("japanese_clothes|chinese_clothes|korean_clothes|vietnamese_clothes|indian_clothes|traditional_clothes|contemporary|casual|formal|formal_clothes|sportswear|workwear|military|winter_uniform|summer_uniform|winter_clothes|summer_clothes|gothic_lolita|sweet_lolita|classic_lolita|wa_lolita|qi_lolita|lolita_fashion|punk|gothic|gyaru|himegyaru|ouji_fashion|lolita_boy|visual_kei|androgynous_clothes|unisex_clothes", "clothing.detail")
register("barefoot", "body.visible", phrase="bare feet", excludes=("slot:footwear", "slot:legwear"))
register("bare_shoulders", "body.visible", phrase="exposed shoulders", excludes=("coverage:nude", "coverage:topless"))
register("bare_arms|bare_legs|bare_back|collarbone|navel|midriff|stomach|thighs|feet|toes|legs|arms|armpits|back|knees|elbows|wrists|hands|fingers|palms|soles|heel|heels|neck|shoulders|pectorals|abs|cleavage|sideboob|underboob|breasts", "body.visible")
EXPLICIT[key("breasts")]["excludes"] = ["body.breast_size:flat_chest"]
register("nipples|areolae|areola_slip|covered_nipples|penis|pussy|anus|testicles|groin|pubic_hair|female_pubic_hair|male_pubic_hair|erection|breasts_out|completely_nude", "body.visible", adult=True)
EXPLICIT[key("completely_nude")] = primitive("completely_nude", "coverage", phrase="fully nude", adult=True,
    excludes=tuple("slot:" + name for name in ("outfit", "top", "bottom", "outerwear", "underwear", "underwear.top", "underwear.bottom")))
register("muscular|muscular_male|muscular_female|toned|toned_male|toned_female|curvy|plump|fat|overweight|obese|skinny|thin|slender|emaciated|thick_thighs|thigh_gap|wide_hips|narrow_waist|wide_waist|broad_shoulders|narrow_shoulders|long_legs|short_legs|long_arms|long_fingers|large_hands|small_hands|large_feet|small_feet|large_head|small_head|big_belly|pot_belly|beer_belly|muffin_top|shiny_skin|shiny_hair|shiny_clothes|oiled_skin|colored_skin", "body.shape")
register("makeup|lipstick|eyeshadow|mascara|eyeliner|eyeliner_wings|eye_makeup|face_paint|full-face_blush|nose_blush|blush_stickers|cheek_blush|nail_polish|fingernails|toenails|colored_nails|manicure|pedicure|sweat|sweatdrop|very_sweaty|nervous_sweating|steaming_body|drooling|drool|saliva|teeth|upper_teeth_only|lower_teeth_only|sharp_teeth|serrated_teeth|buck_teeth|fang|fangs|long_tongue|forked_tongue|tongue|tattoo|bandaid|bandages|bandaged_arm|bandaged_leg|bandaged_hand|injury|bruise|bruises|wound|wounds|scar|scar_on_cheek|facial_tattoo|body_markings|body_writing|scales|scaly_skin", "body.detail")
register("animal_ear_fluff|colored_inner_animal_ears|extra_ears|no_humans|fake_animal_ears|fake_horns|fake_tail|ears_down|ears_up|floppy_ears|droopy_ears|horizontal_ears|low_wings|head_wings|ankle_wings|arm_wings|mechanical_wings|angel_wings|bat_wings|bird_wings|crystal_wings|multiple_wings|extra_wings|single_wing|single_horn|multiple_tails|forked_tail|fin|fins|gills|mechanical_arms|mechanical_legs|mechanical_hands|robot_joints|robot_ears|horn_ornament|animal_nose|claws|hooves|halo", "body.detail")
# "No humans" describes the image, not a trait on a human subject.
EXPLICIT.pop(key("no_humans"))
register("symbol-shaped_pupils|heart-shaped_pupils|star-shaped_pupils|cross-shaped_pupils|diamond-shaped_pupils|flower-shaped_pupils|x-shaped_pupils|rabbit-shaped_pupils|button_eyes|mechanical_eyes|mechanical_eye|single_mechanical_eye|artificial_eye|third_eye|disembodied_linked_eye|extra_eyes|mismatched_pupils|slit_pupils|constricted_pupils|horizontal_pupils|no_pupils|no_sclera|no_eyes|glowing_eyes|glowing_eye|sparkling_eyes|bright_pupils|empty_eyes|blank_eyes|ringed_eyes|solid_eyes|solid_oval_eyes|solid_circle_eyes|solid_circle_pupils|compound_eyes|cephalopod_eyes|symbol_in_eye|heart_in_eye|star_in_eye|flower_in_eye|bags_under_eyes|thick_eyelashes|lower_eyelashes_only|colored_eyelashes|tsurime|tareme|jitome|upturned_eyes|v-shaped_eyes|wavy_eyes|hollow_eyes|bloodshot_eyes|covered_eyes|eyes_visible_through_hair", "eyes.detail")
register("v-shaped_eyebrows|raised_eyebrow|raised_eyebrows|raised_inner_eyebrows|furrowed_brow|short_eyebrows|thick_eyebrows|thin_eyebrows|hikimayu|no_eyebrows|eyebrows_visible_through_hair|partially_shaded_face|shaded_face|nose_shadow|triangle_mouth|heart-shaped_mouth|cat_mouth|animal_mouth|no_nose|no_mouth|naughty_face|crazy_eyes|wide-eyed|narrowed_eyes|rolling_eyes", "face.detail")
register("floating_hair|wet_hair|blunt_ends|long_bangs|short_bangs|medium_bangs|long_sidelocks|blunt_sidelocks|center-flap_bangs|wispy_bangs|parted_hair|hair_down|hair_up|big_hair|hair_over_eyes|one_eye_covered|eyebrows_hidden_by_hair|single_hair_streak|colored_bangs|colored_tips|dyed_bangs|huge_ahoge|heart_ahoge|side_ahoge|hair_extensions|hair_rings|hair_ears|tentacle_hair|snake_hair|feather_hair|fiery_hair|liquid_hair|pointy_hair|low-tied_sidelocks|bangs_pinned_back|hair_strand|lone_nape_hair|hair_tuft|expressive_hair|prehensile_hair|hair_on_horn|braided_bangs|braided_sidelocks|drill_sidelocks|long_hair_between_eyes|multiple_hair_bows|hair_tucking|tucked_hair|hair_spread_out|hair_flowing_over", "hair.detail", excludes=("hair.length:bald",))
register("low-tied_long_hair|low-braided_long_hair|curtained_hair|single_side_bun|half_up_braid|half_crown_braid|folded_ponytail|cone_hair_bun|braided_hair_rings|multi-tied_hair|bun_with_braided_base|front_ponytail|drill_ponytail|high_side_ponytail|low_side_ponytail|wide_ponytail|side_up_bun|nape_braid|braided_twintails|donut_hair_bun|split_ponytail|half_up_half_down_braid|tri_braids|quad_braids|short_twin_braids|long_twintails", "hair.style", excludes=("hair.length:bald", "hair.length:very_short_hair"))
register("confident|determined|shy|flustered|worried|panicking|distress|despair|lonely|disappointed|unamused|skeptical|thinking|pensive|sulking|depressed|frustrated|exhausted|drunk|pain|glaring|scowl|grimace|gloom_(expression)|ecstasy|envious|envy|guilt|disdain|smirk|doyagao|torogao|kubrick_stare|fighting_spirit|blowing_raspberry|puffy_cheeks|cheek_puff", "expression")
register("parted_lips", "mouth", phrase="slightly parted")
register("tongue_out", "face.detail", phrase="a tongue sticking out")
register("clenched_teeth", "mouth", phrase="closed with clenched teeth")
register(":d|;d|:o|:3|:p|;p|:>|:c|:t|:q|:s|:v|:x|:i|:>|:}|:)|:(|;)|>_<|>_o|^_^|^^^|o_o|0_0|=_=|t_t|u_u|w|+++|+_+|@_@|:3:|3:|d:", "expression")
for tag, phrase in {":d": "an open-mouthed smile", ";d": "a winking open-mouthed smile", ":o": "a surprised round-mouthed expression", ":3": "a playful cat-like smile", ":p": "a playful expression with the tongue out", ";p": "a winking expression with the tongue out", ":>": "a pointed smiling mouth", ":c": "a downturned mouth", ":t": "a flat-mouth expression", ":q": "a tongue licking an upper lip", ":s": "an uneasy expression", ":v": "a wide V-shaped mouth", ":x": "a sealed mouth", ":i": "a straight mouth", ":}": "a curved smile", ":)": "a smile", ":(": "a frown", ";)": "a winking smile", ">_<": "an expression with tightly shut eyes", ">_o": "an expression with one tightly shut eye", "^_^": "a smile with closed eyes", "^^^": "a catlike grin", "o_o": "a wide-eyed expression", "0_0": "a surprised wide-eyed expression", "=_=": "a tired expression", "t_t": "a crying expression", "u_u": "an expression with lowered eyelids", "w": "a W-shaped mouth", "+++": "a determined expression", "+_+": "a sparkling-eyed expression", "@_@": "a dizzy expression", ":3:": "a cat-like smile", "3:": "a pout", "d:": "an alarmed open-mouthed expression"}.items():
    EXPLICIT[key(tag)]["phrase"] = phrase
for tag in (":d", ";d", ":o", ":p", ";p", ":v", "d:"):
    EXPLICIT[key(tag)]["requires"] = ["mouth:open_mouth"]
register("leaning_forward|leaning_back|leaning|arched_back|bent_over|bending_over|stretching|trembling|shrugging|facing_away|facing_viewer|facing_sideways|head_rest|head_tilt|looking_at_hand|looking_at_self|looking_at_own_hand|looking_at_food|looking_at_object|looking_at_phone", "action")
register("v|double_v|v_arms|clenched_hand|clenched_hands|open_hand|own_hands_together|heart_hands|claw_pose|paw_pose|thumbs_up|thumbs_down|index_finger_raised|middle_finger|pinkie_out|pinky_out|pointing_at_self|finger_gun|finger_guns|finger_to_mouth|outstretched_hand|outstretched_hands|outstretched_arm|outstretched_arms|spread_arms|reaching_towards_viewer|arms_behind_head|arm_behind_head|arm_behind_back|arm_at_side|hands_on_own_hips|hand_on_own_chest|hands_on_own_chest|hand_on_own_face|hands_on_own_face|hand_on_own_cheek|hand_on_own_chin|hand_on_own_head|hand_on_own_arm|hand_on_own_thigh|hand_on_own_knee|hands_on_own_knees|hand_on_own_wrist|hand_on_own_neck|hand_on_own_shoulder|hand_on_own_back|hand_on_own_stomach|hand_on_own_leg|hand_in_pocket|hands_in_pockets|hand_in_own_hair|hands_in_own_hair|hands_on_headwear|covering_own_mouth|shading_eyes|salute|double_salute|bowing|curtsey|curtsy", "hands.pose")
register("spread_legs|legs_apart|legs_together|crossed_legs|leg_up|legs_up|knee_up|knees_up|knees_together_feet_apart|knees_together|standing_on_one_leg|leg_lift|standing_split|contrapposto|tiptoes|tiptoe|ankle_support|ankles_crossed|folded_legs|kneeling_on_one_knee|leg_behind_head|foot_up|feet_up|heel_up|heels_up|heel_lift|bent_knee|bent_knees|knees_apart|legs_over_head", "legs.pose")
register("all_fours|dogeza|leaning_against_wall", "posture")
register("flying|floating|jumping|dancing|spinning|stretching|swimming|wading|falling|hopping|skipping|crawling|climbing|crawling_forward|sprinting|jogging|sleeping|yawning|sneezing|coughing|sighing|whistling|singing|laughing|cheering|clapping|facepalm|wiping_tears|brushing_hair|combing_hair|tying_hair|adjusting_hair|tucking_hair|twirling_hair|playing_with_own_hair|adjusting_eyewear|adjusting_headwear|adjusting_necktie|adjusting_gloves|selfie|fishing|cooking|baking|writing|drawing|painting|playing_video_games|playing_instrument|smoking|eating|drinking|holding|holding_weapon|dual_wielding", "action")
for tag, prop in {"eating": "food", "drinking": "drink", "smoking": "cigarette", "reading": "book", "selfie": "smartphone", "brushing_hair": "hair_brush", "combing_hair": "comb", "fishing": "fishing_rod", "cooking": "food", "baking": "food", "writing": "pen", "drawing": "pencil", "painting": "paintbrush", "playing_video_games": "game_controller", "playing_instrument": "instrument", "holding_weapon": "weapon", "dual_wielding": "weapon"}.items():
    if key(tag) in EXPLICIT:
        EXPLICIT[key(tag)]["requires"] = ["object:" + prop]
for tag in ("jumping", "flying", "swimming", "crawling", "sprinting", "jogging"):
    EXPLICIT[key(tag)]["excludes"] = ["posture:" + pose for pose in ("standing", "sitting", "lying", "kneeling", "crouching", "squatting")]
EXPLICIT[key("sleeping")]["requires"] = ["eyes.state:closed_eyes"]
EXPLICIT[key("swimming")]["requires"] = ["scene.detail:water"]
EXPLICIT[key("wading")]["requires"] = ["scene.detail:water"]
for tag, prop, pose in (("on_bed", "bed", "lying"), ("on_chair", "chair", "sitting"), ("on_bench", "bench", "sitting"), ("on_couch", "sofa", "sitting"), ("on_stool", "stool", "sitting"), ("sitting_on_stairs", "stairs", "sitting")):
    register(tag, "placement", phrase=f"positioned on {'stairs' if prop == 'stairs' else 'a ' + prop}", requires=(("scene.detail:" if prop == "stairs" else "object:") + prop,))
register("on_floor|on_ground", "placement", phrase="positioned on the ground")
for tag, prop in (("against_wall", "wall"), ("against_tree", "tree"), ("against_railing", "railing"), ("against_window", "window"), ("against_glass", "glass"), ("under_table", "table")):
    register(tag, "placement", phrase="positioned " + tag.replace("_", " ").replace(prop, "a " + prop), requires=(("object:" if prop in {"table", "glass"} else "scene.detail:") + prop,))
register("blurry|blurry_foreground|blurry_background|motion_blur|depth_of_field|bokeh|foreshortening|perspective|straight-on|upside-down|pov|pov_hands|portrait|tachi-e|profile|cropped_torso|cropped_legs|feet_out_of_frame|foot_out_of_frame|head_out_of_frame|eyes_out_of_frame|knees_out_of_frame|out_of_frame|zoom_layer|chibi_inset|character_profile|reference_sheet|expression_chart|multiple_views|multiple_expressions|split_screen|inset|letterboxed|letterboxing|outside_border|segmented_comic|right-to-left_comic|vertical_scroll_comic|full_page_comic", "framing")
register("male_focus|female_focus|solo_focus|animal_focus|pokemon_focus|other_focus|object_focus|creature_focus|monster_focus|mecha_focus|food_focus|vehicle_focus|weapon_focus|flower_focus|sky_focus|hand_focus|foot_focus|back_focus|hip_focus|thigh_focus|armpit_focus|breast_focus|crotch_focus|ass_focus|pectoral_focus|reflection_focus|text_focus|eye_focus", "focus")
register("chibi|super_deformed|3d|3d_render|traditional_media|watercolor_(medium)|pencil_(medium)|watercolor_pencil_(medium)|colored_pencil_(medium)|marker_(medium)|oil_painting_(medium)|acrylic_paint_(medium)|pastel_(medium)|chalk_(medium)|crayon_(medium)|charcoal_(medium)|ink_(medium)|graphite_(medium)|photo_(medium)|photograph_(medium)|paper_cutout|collage|oekaki|retro_artstyle|sketch|rough_sketch|lineart|clean_lineart|colored_sketch|limited_palette|limited_color|monochrome|greyscale|sepia|partially_colored|spot_color|flat_color|flat_colors|cel_shading|soft_shading|hatching|crosshatching|halftone|screentones|stippling|dithering|pointillism|high_contrast|low_contrast|highres|lowres|absurdres|colorful|muted_colors|pastel_colors|neon_colors|vibrant_colors|warm_colors|cool_colors|silhouette|outline|comic|silent_comic|1koma|2koma|3koma|4koma|5koma|6koma|multiple_4koma|sumi-e|ukiyo-e|impasto|art_nouveau|art_deco|pixel_art|voxel_art|clay_(medium)|sculpture|paper_craft", "style")
register("sunlight|moonlight|starlight|ambient_light|diffused_lighting|dappled_sunlight|spotlight|chiaroscuro|lens_flare|bloom|sparkle|glowing|shine|glint|sparkles|light_particles|light_rays|god_rays|volumetric_lighting|colored_lighting|neon_lighting|fluorescent_lighting|candlelight|firelight|dim_lighting|dark|shade|shadow|shadows|strong_shadows|cast_shadow|hard_shadow|soft_shadow|no_shadow|reflection|reflective|mirror_image|silhouette|bounce_light|sunbeam|light_beam", "lighting")
register("simple_background|white_background|black_background|grey_background|red_background|pink_background|orange_background|yellow_background|green_background|blue_background|purple_background|brown_background|aqua_background|transparent_background|dark_background|gradient_background|two-tone_background|multicolored_background|colorful_background|rainbow_background|abstract_background|striped_background|vertical-striped_background|horizontal-striped_background|diagonal-striped_background|polka_dot_background|floral_background|flower_background|heart_background|star_symbol_background|starry_background|starry_sky_background|checkered_background|argyle_background|plaid_background|grid_background|text_background|sparkle_background|bubble_background|halftone_background|patterned_background|photo_background|fiery_background|3d_background", "background")
register("sky|cloud|blue_sky|cloudy_sky|night_sky|starry_sky|gradient_sky|orange_sky|purple_sky|red_sky|grey_sky|grey_clouds|cumulonimbus_cloud|moon|full_moon|crescent_moon|crescent|red_moon|blood_moon|blue_moon|sun|water|ocean|sea|river|lake|pond|underwater|space|nature|horizon|mountainous_horizon|fire|blue_fire|purple_fire|smoke|steam|tree|trees|plant|plants|grass|petals|falling_petals|falling_leaves|cherry_blossoms|autumn_leaves|bamboo|mushroom|flowers|flower_field|bush|rose_bush|wooden_floor|tile_floor|floor|reflective_floor|wall|brick_wall|window|open_window|door|open_door|railing|fence|wooden_fence|chain-link_fence|stairs|stone_steps|tatami|tiles|building|buildings|architecture|cityscape|bookshelf|sand|rock|ice|water_drop|reflective_water|snowflake|snowflakes|rainbow|aurora|meteor|comet", "scene.detail")
register("heart|star_(symbol)|cross|cross_(symbol)|arrow_(symbol)|emphasis_lines|motion_lines|speed_lines|action_lines|sound_effects|speech_bubble|thought_bubble|spoken_heart|spoken_question_mark|spoken_exclamation_mark|spoken_blush|spoken_ellipsis|spoken_sweatdrop|spoken_musical_note|spoken_anger_vein|spoken_object|spoken_food|spoken_star|spoken_flower|spoken_light_bulb|floating_heart|floating_symbol|anger_vein|heart_eyes|music|musical_note|musical_notes|question_mark|exclamation_mark|interrobang|ellipsis|squiggle|squiggles|light_bulb|zzz|!!|!!!|!?|?!|?|!|~|♪|♥|★", "symbol")
register("artist_name|signature|watermark|twitter_username|character_name|company_name|dated|text|english_text|japanese_text|chinese_text|korean_text|french_text|german_text|russian_text|spanish_text|italian_text|arabic_text|latin_text|thai_text|portuguese_text|bilingual|multilingual|censored_text|engrish_text|text_focus|commentary|chat_log|speech_bubble|thought_bubble", "text")
register("censored|mosaic_censoring|bar_censor|bar_censoring|heart_censor|star_censor|blur_censor|blank_censor|black_censor|white_censor|censor_bar|censor_blur|censor_mosaic|convenient_censoring|light_censor|steam_censor|hair_censor|blood|blood_splatter|splatter|blood_stain|bloodstain|frost|frosted|dust|embers|snow|rain|wind|fog|mist|water_splash|splash|splashing|ripples|water_ripples|floating_particles", "effect")
register("weapon|polearm|instrument|food|drink|fishing_rod|stiletto_(weapon)|glaive_(polearm)|arrow_(projectile)|poke_ball|poke_ball_(basic)|rigging|turret|ship_turret|military_vehicle|condom_wrapper|pocky|jack-o'-lantern|towel|card_(medium)|poster_(medium)|photograph_(object)|drawing_(object)|painting_(object)|statue|skeleton|syringe|soap|lotion|sponge|chess_piece|paper_bag|carton|can|condom|dildo|vibrator|sex_toy|anal_beads|ball_gag|gag|handcuffs|shackles|leash|restraints", "object")
register("cigarette|fan|feather|feathers|pouch|reins|nunchaku|stapler|computer_tower|cassette_player|scouter|portal_(object)|gap_(touhou)|tonfa|naginata|sakazuki|box_of_chocolates|weighing_scale|fumo_(doll)|aiguillette|belt_buckle|gasmask|gas_mask|eyepiece|control_panel|life_preserver|buoy", "object")
register("collar|mask|piercing|ear_piercing|facial_piercing|single_earring|single_glove|single_thighhigh|single_sock|single_kneehigh|single_shoe|single_boot|eyewear_on_head|eyewear_on_hair|glasses_on_head|hat_on_head|bandana|bandanna|loose_thighhigh|loose_sock|loose_socks|loose_kneehigh|single_epaulette", "accessory")
register("skin_tight|skindentation|strap_slip|double_strap_slip|skirt_set|multicolored_clothes|two-tone_clothes|layered_clothes|layered_skirt|frilled_straps|neck_strap|underwear_peek|bra_peek|bra_strap|panty_peek|undergarment_lines|bralines|pantylines|reverse_outfit", "clothing.detail")
register("arm_support|slouching|sway_back|twisted_torso|balancing|midair|fetal_position|hugging_own_legs|reclining|straddling|thigh_straddling|upright_straddle|prostration|cowering|faceplant|fighting_stance|handstand|one_arm_handstand|yoga|split|standing_split|dorsiflexion|plantar_flexion|pigeon-toed|toe_scrunch|knees_apart_feet_together|bowlegged_pose|rabbit_pose|ghost_pose|zombie_pose|ojou-sama_pose|gendou_pose|henshin_pose|jojo_pose|a-pose|t-pose|w_arms|watson_cross", "posture")
EXPLICIT[key("reclining")]["requires"] = ["posture:sitting"]
register("looking_ahead|sideways_glance|staring|looking_at_arms|looking_at_legs|looking_at_feet|looking_at_wings|looking_at_tail", "gaze")
register("light_smile|nervous_smile|forced_smile|smile_(\")|side_smile|evil_grin|wide_smile|grinning|crying_with_eyes_open|crying_with_eyes_closed|happy_tears|tearing_up|smiling_while_crying|blinking|xd|x_x|akanbe|ahegao|fucked_silly", "expression")
EXPLICIT[key("crying_with_eyes_open")]["features"] = {"eyes.state": "open"}
EXPLICIT[key("crying_with_eyes_closed")]["requires"] = ["eyes.state:closed_eyes"]
EXPLICIT[key("ahegao")]["adult"] = True
EXPLICIT[key("fucked_silly")]["adult"] = True
register("copyright_name|copyright_notice|credits|kanji|hiragana|katakana|hangeul|hangeul_text|date|timestamp|caption|subtitles|subtitle|speech_bubble|comic_sound_effects|text_box|author_name", "text")
register("notice_lines|drawn_heart|beamed_eighth_notes|eighth_note|quarter_note|sixteenth_note|bass_clef|treble_clef|iron_cross|peace_symbol|three_dots|four-pointed_star|sparkle_symbol", "symbol")
register("parody|art_parody|cover|cover_page|novel_cover|manga_cover|comic_cover|game_cover|album_cover|dvd_cover|box_art|novel_illustration|deformed|jaggy_lines|symmetry|asymmetry|isometric|comic_inset|reference_inset|photo_inset|game_screenshot_inset|official_art_inset|sticker_(medium)|poster_(medium)|dakimakura_(medium)|child's_drawing|sugimori_ken_(style)", "style")
register("temple|synagogue|mosque|bakery|veranda|porch|skyscraper|hangar|greenhouse|courtyard|shopping_mall|town_square|railway_station|train_station|bus_stop|tram_stop|bus_interior|aircraft_interior|spaceship_interior|ship_interior|car_interior|submarine_interior|gym_storeroom|storeroom|school_rooftop|school_hallway|school_gym|schoolyard", "location")
register("star_(sky)|dust_cloud|boulder|mountains|stones|stone|ruins|desert|raincloud|dark_clouds|green_sky|lightning|meteor_shower|snowdrift|snow_cover|pool|riverbank|shore|seashore|foamy_waves|white_petals|red_petals|pink_petals|rose_petals|haze|ash|glowing_particles", "scene.detail")
for tag in ("condom", "dildo", "vibrator", "sex_toy", "anal_beads", "ball_gag", "gag", "restraints"):
    EXPLICIT[key(tag)]["adult"] = True
EXPLICIT[key("fur")]["slot"] = "body.detail"
for tag in ("shiny_clothes",):
    EXPLICIT[key(tag)]["slot"] = "clothing.detail"
for tag in ("breasts", "cleavage", "sideboob", "underboob", "breast_focus", "crotch_focus", "ass_focus", "naughty_face", "ecstasy", "torogao"):
    EXPLICIT[key(tag)]["adult"] = True
EXPLICIT[key("clenched_teeth")] = primitive("clenched_teeth", "face.detail", phrase="clenched teeth")
EXPLICIT[key("^^^")] = primitive("^^^", "symbol", phrase="a crown-shaped surprise mark")
EXPLICIT[key("+++")] = primitive("+++", "symbol", phrase="a laughter symbol")
EXPLICIT[key("w")] = primitive("w", "hands.pose", phrase="a hand gesture with three fingers extended")
EXPLICIT[key(":>")]["phrase"] = "a closed-mouth V-shaped smile"
EXPLICIT[key(":>")]["requires"] = ["mouth:closed_mouth"]
EXPLICIT[key("^_^")]["phrase"] = "a cheerful expression with upward-curving closed eyes"
EXPLICIT[key("^_^")]["requires"] = ["eyes.state:closed_eyes"]
EXPLICIT[key('xd')]['phrase'] = 'a laughing face with tightly closed X-shaped eyes'
EXPLICIT[key('xd')]['requires'] = ['eyes.state:closed_eyes']
EXPLICIT[key('x_x')]['phrase'] = 'an expression with X-shaped eyes'
for tag in ('underwear_peek', 'bra_peek', 'bra_strap', 'panty_peek', 'bralines', 'pantylines', 'undergarment_lines'):
    EXPLICIT[key(tag)]['adult'] = True
    EXPLICIT[key(tag)]['required_slots'] = [['underwear', 'underwear.top', 'underwear.bottom']]
for tag in ('eyewear_on_head', 'eyewear_on_hair', 'glasses_on_head'):
    EXPLICIT[key(tag)] = primitive(tag, 'placement', phrase='glasses resting on the head', requires=('object:glasses',))
# A generic straddle needs a target and cannot be an isolated posture.
for tag in ('straddling', 'thigh_straddling', 'upright_straddle'):
    EXPLICIT.pop(key(tag), None)


def explicit_rule(name, page):
    normalized = key(name)
    if normalized not in EXPLICIT:
        return None, None
    raw = definition(page.get("body", ""))
    meaning = plain(raw)
    if not meaning or re.match(r"(?:ambiguous|deprecated|obsolete|invalid)\b", meaning, re.I):
        return None, None
    rule = {**EXPLICIT[normalized]}
    rule["adult"] = rule["adult"] or bool(ADULT.search(normalized))
    if rule["slot"] == "action" and not rule["phrase"].endswith("ing") and normalized in {"holding", "dual wielding"}:
        rule["phrase"] = "holding an object" if normalized == "holding" else "holding a weapon in each hand"
    return rule, {"family": "explicit_attribute_or_gesture", "definition": meaning[:600], "passage": raw[:900]}


def relational_rule(name, page):
    """Directional roles use ordered actor IDs, never a plural symmetric verb."""
    normalized = key(name)
    raw = definition(page.get("body", ""))
    if not raw:
        return None, None
    body_parts = r"head|face|cheek|chin|neck|shoulder|arm|wrist|hand|chest|back|waist|hip|stomach|thigh|knee|leg|foot|hair|breast"
    match = re.fullmatch(r"(hand|hands) on another's (" + body_parts + r")", normalized)
    if match:
        noun, part = match.groups()
        rule = primitive(name, "interaction", actors=2, adult=part == "breast")
        rule["role_phrase"] = "{0} rests " + ("a hand" if noun == "hand" else "both hands") + " on {1}'s " + part
    elif normalized in {"looking at another", "pointing at another", "facing another", "headpat", "hug from behind", "arm hug", "sitting on lap", "sitting on person", "piggyback", "princess carry", "kiss", "imminent kiss", "cheek kiss", "forehead kiss", "hand kiss", "blowing kiss", "high five", "handshake", "interlocked fingers", "locked arms", "helping", "flirting", "dancing together"}:
        phrases = {
            "looking at another": "{0} looks at {1}", "pointing at another": "{0} points at {1}",
            "facing another": "{0} faces {1}", "headpat": "{0} pats {1}'s head",
            "hug from behind": "{0} hugs {1} from behind", "arm hug": "{0} hugs {1}'s arm",
            "sitting on lap": "{0} sits on {1}'s lap", "sitting on person": "{0} sits on {1}",
            "piggyback": "{0} carries {1} on their back", "princess carry": "{0} carries {1} in both arms",
            "cheek kiss": "{0} kisses {1}'s cheek", "forehead kiss": "{0} kisses {1}'s forehead", "hand kiss": "{0} kisses {1}'s hand",
            "blowing kiss": "{0} blows a kiss toward {1}", "imminent kiss": "{0} and {1} are about to kiss",
        }
        rule = primitive(name, "interaction", actors=2)
        if normalized in phrases:
            rule["role_phrase"] = phrases[normalized]
        else:
            rule["phrase"] = {"kiss": "kissing each other", "high five": "giving each other a high five", "handshake": "shaking hands", "interlocked fingers": "holding hands with fingers interlocked", "locked arms": "linking arms", "helping": "helping each other", "flirting": "flirting with each other", "dancing together": "dancing together"}[normalized]
    else:
        return None, None
    return rule, {"family": "ordered_interaction", "definition": plain(raw)[:600], "passage": raw[:900]}
