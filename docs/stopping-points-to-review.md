# Steps that need a stopping point

Historical review below. Current status and instructions are in
`remaining-milestones.md`; most entries below now have source-verified goals.
Do not apply this old panel-boundary recipe without checking the current data.

Each of these tells the player to run a quest until something the quest's
own progress value cannot see, and the guide's next step for that quest is
not the one that finishes it -- so there is nothing for the build to hand
over to. 23 of the guide's 47 "until" steps; the other 24 are answered.

To answer one, put its step id in `curated/overrides.yaml` with the number
of the Quest Helper step the guide hands over AT -- the first one the guide
is no longer asking for:

```yaml
steps:
  <step id>:
    questDoneAtPanel: <number>
```

Leave one out and it behaves as it does today: it guides correctly and
waits to be ticked by hand.


## Bank 27 -- Continue Prince Ali Rescue until you need to return to Osman

    id: f769b86e2b        quest: princealirescue

     0  Talk to Hassan in the Al Kharid Palace.
     1  Talk to Osman north of the Al Kharid Palace.
     2  Have Ned in Draynor Village make you a wig from 3 balls of wool. He can also sell you a rope for
     4  Talk to Aggie in Draynor Village to get some paste.
     5  Talk to Keli in the jail east of Draynor Village. If you've already made the key mould, open the
     8  Bring everything to the jail and give Joe there three beers.
     9  Use rope on Keli.
    10  Use the key on the prison door. If Lady Keli respawned you'll need to tie her up again.
    11  Talk to Prince Ali and free him.
    12  Return to Hassan in the Al Kharid Palace to complete the quest.

## Bank 45 -- Kill Men/Women by Bob's Axes until 3x Grimy Guam, 2x Grimy Marrentil & 1x Harralander[Tick Manipulation/Bone Voyage/One Small Favour]

    id: 15e5759aa8        quest: onesmallfavour

     0  Talk to Yanni Salika in Shilo Village. CKR fairy ring or take cart from Brimhaven.
     1  Talk to a Jungle Forester south of Shilo Village.
     2  Talk to Brian in the Port Sarim axe shop.
     3  Talk to Aggie in Draynor Village.
     4  Talk to Johanhus Ulsbrecht in the south of the H.A.M hideout.
     5  Talk to Fred the Farmer north of Lumbridge.
     6  Talk to Seth Groats in the farm north east of Lumbridge, across the river.
     7  Talk to Horvik in the armour shop north east of the Varrock square.
     8  Talk to the Apothecary in west Varrock.
     9  Talk to Tassie Slipcast in the Barbarian Village pottery building.
    10  Talk to Hammerspike Stoutbeard in the west cavern of the Dwarven Mine.
    11  Talk to Sanfew upstairs in the Taverley herblore store.
    13  Right-click talk to Captain Bleemadge on White Wolf Mountain.
    14  Talk to Arhein in Catherby.
    15  Talk to Phantuwti in the south west house of Seers' Village.
    16  Enter the cave south east of the Fishing Guild.
    17  Right-click search the sculpture in the wall in the north east corner of the cave.
    18  Talk to Wizard Cromperty in north east Ardougne.
    19  Talk to Tindel Marchant in Port Khazard.
    20  Talk to Rantz in the Feldip Hills. AKS fairy ring or Feldip Hills Teleport.
    21  Talk to Gnormadium Avlafrim west of Rantz.
    23  Talk to Gnormadium Avlafrim again.
    24  Return to Rantz in the Feldip Hills. AKS fairy ring or Feldip Hills Teleport.
    25  Return to Tindel Marchant in Port Khazard.
    26  Return to Wizard Cromperty in north east Ardougne.
    27  Get 5 pigeon cages from behind Jerico's house in central East Ardougne.
    28  Enter the cave south east of the Fishing Guild. Be prepared to fight the Slagilith(level 92, tak
    29  Use the animate rock scroll next to the sculpture in the north east cavern.
    33  Return to Phantuwti in the south west house of Seers' Village.
    34  Right-click search the weathervane on top of the Seers' building.
    35  Use a hammer on the weathervane.
    36  Right-click search the weathervane on top of the Seers' building again.
    37  Repair the vane parts on an anvil. You can find one in the north of Seers' Village.
    38  Go back up to the Seers' roof and fix the vane.
    39  Return to Phantuwti in the south west house of Seers' Village.
    40  Talk to Arhein in Catherby.
    41  Right-click talk to Captain Bleemadge on White Wolf Mountain.
    42  Return to Sanfew upstairs in the Taverley herblore store.
    43  Return to Hammerspike Stoutbeard in the west cavern of the Dwarven Mine.
    44  Kill 3 dwarf gang members until Hammerspike gives in. One dwarf gang member should appear after
    46  Return to Tassie Slipcast in the Barbarian Village pottery building.
    47  Spin the clay into a pot lid.
    48  Fire the unfired pot lid.
    49  Get a pot to put your lid on. There's one in the Barbarian Village helmet shop.
    50  Use the pot lid on a pot.
    51  Return to the Apothecary in west Varrock.
    52  Return to Horvik in the armour shop north east of the Varrock square.
    53  Talk to Horvik once more in the armour shop north east of the Varrock square.
    54  Return to Seth Groats in the farm north east of Lumbridge, across the river.
    55  Return to Johanhus Ulsbrecht in the south of the H.A.M hideout.
    56  Return to Aggie in Draynor Village.
    57  Return to Brian in the Port Sarim axe shop.
    58  Return to a Jungle Forester south of Shilo Village. CKR fairy ring or take cart from Brimhaven.
    59  Return to Yanni Salika in Shilo Village.

## Bank 85 -- Make Swords until until 731,000 Smithing XP. You will need to repeat the Mithril Claw & Steel Warhammer/Battleaxe steps to maintain. You should profit roughly 1M from Smithing which is a hard requirement for Song of the Elves. 70 is finished on Between a Rock quest.

    id: 90ced4b5c5        quest: betweenarock

     0  Talk to Dondakan in the north of the mine.
     1  Talk to the Dwarven Engineer in west Keldagrim.
     2  Talk to Rolad at the Ice Mountain entrance to the Dwarven Mine. If you don't have an ammo mould,
     3  Enter the Dwarven Mine.
     4  Search the mine carts for a page.
     5  Kill scorpions for a page.
     6  Mine low level rocks for a page.
     7  Talk to Rolad again.
     8  Read the entire dwarven lore book.
     9  Return to Dondakan with the book and a gold bar.
    10  Use a gold bar on Dondakan.
    11  Use a gold bar on a furnace to make a gold cannonball.
    12  Use a gold cannon ball on Dondakan.
    13  Read the last page of the dwarven lore book again for a base schematic.
    14  Talk to the Dwarven Engineer in west Keldagrim.
    15  Use 3 gold bars on an anvil to make a gold helmet.
    16  Talk to Khorvak under White Wolf Mountain.
    17  Assemble the schematics.
    18  Prepare for a fight, then return to Dondakan.
    19  Mine 6 gold ores. If you want the Avatar to be level 75 vs 125, get 15. Keep these in your inven
    20  TALK to the central wall of flame.
    22  Talk to Dondakan to finish the quest.

## Bank 96 -- Continue Animal Magnetism at the Farm until needing to go to the Old Crone

    id: 08975f4fbc        quest: animalmagnetism

     0  Talk to Ava to begin the quest.
     1  Talk to Malcolm at the farm west of the Ectofuntus.
     2  Talk to Alice.
     3  Talk to Malcolm again.
     4  Talk to Alice again.
     5  Talk to the Old crone just east of the Slayer Tower twice.
     6  Give the Crone-made amulet to Malcolm.
     7  Talk to Malcolm again to watch a cutscene.
     8  Buy two undead chickens from Malcolm. You can acquire ecto-tokens using the Ectofuntus to the ea
     9  Give the two Undead chickens to Ava.
    10  Talk to the witch in the manor twice.
    11  Go to the iron mine in Rimmington northeast of the house portal.
    12  While looking north, use the hammer on the Selected iron.
    13  Give the Bar magnet to Ava.
    14  Try to chop an undead tree outside Draynor manor.
    15  Talk to Turael in Burthorpe twice, giving him the Mithril axe and Holy symbol.
    16  Try to chop an undead tree outside Draynor manor with the Blessed axe until you receive undead t
    17  Give the Undead twigs to Ava.
    18  Talk to Ava to receive the research notes.
    19  Translate the research notes.
    20  Give Ava the translated research notes.
    21  Combine Hard leather and Polished buttons with the pattern.
    22  Give Ava the container.

## Bank 98 -- Head to the Experiment Lair and continue Creature of Fenkenstrain until you get the Conductor Mould

    id: 4ed0ab6edd        quest: creatureoffenkenstrain

     0  Head to the Canifis bar and either buy the pickled brain for 50 coins, or telegrab it.
     1  Talk to Dr. Fenkenstrain to start the quest.
     2  Go up the staircase to grab the items you will need.
     3  Search the nearby bookcase for Handy Maggot Avoidance Techniques.
     4  Search the west bookcase for The Joy of Grave Digging.
     5  Combine the two amulet by using one on the other.
     6  Go back to the ground floor.
     7  Talk to the Gardener Ghost.
     8  Go to the grave of the gardener and dig for his head.
     9  Use the decapitated head on the pickled brain to create a decapitated head.
    10  Use the Star Amulet on the memorial and push it to go in the caves.
    11  Push the memorial south east of the castle.
    12  Kill the level 51 Experiment north-west of the ladder to get a key.
    13  Leave the caves by going north-west, be sure to pick up the key from the level 51 experiment.
    14  Use your spade on this tile to get the torso.
    15  Use your spade on this tile to get arms.
    16  Use your spade on this tile to get legs.
    17  Deliver the body parts to Dr. Fenkenstrain, use a teleport to Fenkenstrain's castle or run back
    18  Get a needle and 5 threads and deliver them to Dr. Fenkenstrain.
    19  Talk to the Gardener Ghost and ask for the shed key.
    20  Open the cupboard and search it for a brush.
    21  Grab 3 canes from the pile.
    22  Use 3 canes on the brush one at a time.
    23  Go up to the second floor of the castle.
    24  Use the extended brush on the fireplace to get the conductor mould.
    25  Go to any furnace make a lightning rod.
    27  Go up to the third floor using the ladder in the middle of the castle.
    28  Repair the lightning Conductor.
    29  Go back to the first floor of the castle and talk to Dr. Fenkenstrain.
    30  Go back to the first floor of the castle and talk to Dr. Fenkenstrain.
    31  Go up to the second floor to confront Fenkenstrain's monster.
    32  Use the Tower Key on the door.
    33  Go up the ladder.
    34  Talk to Fenkenstrain's monster.
    35  Go back to Dr. Fenkenstrain, instead of talking to him right click and pickpocket him.

## Bank 110 -- Continue Family Crest until you have 2x Perfect Gold

    id: d5a2d20554        quest: familycrest

     0  Talk to Dimintheis in south east Varrock.
     1  Talk to Caleb in Catherby.
     2  Talk to Caleb again with the required fish.
     3  Talk to Caleb in Catherby once more.
     4  Talk to the Gem Trader in Al Kharid.
     5  Talk to the man south of the Al Kharid mine.
     6  Talk to Boot in the south western Dwarven Mines.
     7  Enter the old ruin entrance west of Witchaven.
    15  Smelt the perfect gold ore into bars.
    16  Make a perfect ruby necklace at a furnace. Make sure to only craft one.
    17  Make a perfect ruby ring at a furnace. Make sure to only craft one.
    18  Return to the man south of the Al Kharid mine.
    19  Go upstairs in the Jolly Boar Inn north east of Varrock and talk to Johnathon.
    20  Give Johnathon some antipoison.
    21  Kill Chronozon in the south west corner of the Edgeville Wilderness Dungeon. You need to hit him
    22  Combine the 3 crest parts together.
    23  Return the family crest to Dimintheis in south east Varrock.

## Bank 118 -- Talk to Mori and continue Ascent of Arceuus until needing to head to Mount Karuulm

    id: 10da9f91b7        quest: theascentofarceuus

     0  Talk to Mori in Arceuus.
     1  Talk to Councillor Andrews in Kourend Castle.
     2  Return to Mori in Arceuus.
     3  Enter the Tower of Magic in Arceuus, ready to fight some level 16 Tormented Souls.
     5  Go up the stairs in the Tower of Magic.
     6  Talk to Lord Trobin Arceuus.
     7  Talk to Kaal-Ket-Jor.
     8  Inspect the ancient grave south of Mount Karuulm.
     9  Inspect plants and bushes until you uncover the full path.
    10  Inspect the final plant and kill the Trapped Soul (level 30) which appears.
    11  Return to Kaal-Ket-Jor.
    12  Inspect the rocks near the Arceuus Altar until you find a device.
    13  Talk to Lord Trobin Arceuus to finish the quest.

## Bank 118 -- Head West & continue Forsaken Tower until you get Dinh's Hammer

    id: 46faf9e042        quest: theforsakentower

    22  Talk to Lady Vulcana Lovakengj in the south of Lovakengj.
    23  Talk to Undor at the entrance to Wintertodt. If you've never talked to Ignisia before, you'll ne
    24  Enter the Forsaken Tower, west of Lovakengj.
    25  Inspect the display case in the Forsaken Tower.
    26  Climb down the ladder into the tower's basement.
    31  Get the hammer from the display case in the Forsaken Tower.
    32  Return Dinh's Hammer to Undor at the entrance to Wintertodt.
    33  Return to Lady Vulcana in south Lovakengj to finish the quest.

## Bank 118 -- Continue Tale of Righteous until after you need to speak to    Lord Shiro Shayzien

    id: b64f6b40fe        quest: taleoftherighteous

     0  Talk to Phileas Rimor in Shayzien.
     1  Bring a melee weapon, ranged weapon, and runes for magic attacks and teleport with Archeio in th
     2  Talk to Pagida in the Library Historical Archive.
     3  Solve the crystal puzzle.
     8  Investigate the skeleton in the north cell.
     9  Report back to Phileas Rimor in Shayzien.
    10  Talk to Shiro upstairs in the War Tent located on the west side of the Shayzien Encampment.
    11  Travel to Mount Quidamortem and talk to Historian Duffy.
    12  Use a rope on the crevice west side of Quidamortem.
    13  Enter the crevice west side of Quidamortem, ready to fight a corrupted lizardman (level 46).
    16  Attempt to enter the magic gate to the south room. You will need to kill the corrupted lizardman
    17  Inspect the Unstable Altar in the south room.
    18  Return to Historian Duffy.
    19  Enter the crevice west side of Quidamortem again.
    20  Talk to Historian Duffy near the Unstable Altar.
    21  Talk to Gnosi near the Unstable Altar.
    22  Return to Shiro upstairs in the War Tent located on the west side of the Shayzien Encampment.
    23  Return to Phileas Rimor's house in Shayzien.
    24  Return to Shiro upstairs in the War Tent in west Shayzien to complete the quest.

## Bank 119 -- Continue Ratcatchers until needing to go to Keldagrim

    id: 8f0f335851        quest: ratcatchers

     0  Talk to Gertrude west of Varrock.
     1  Go down into Varrock Sewer via the Manhole south east of Varrock Castle.
     2  Talk to Phingspet in Varrock Sewer.
     3  Have your cat catch 8 rats.
     4  Talk to Phingspet in Varrock Sewer again.
     5  Talk to Jimmy Dazzler north of Ardougne Castle.
     6  Read the directions.
     7  Climb the trellis around the back of the mansion, avoiding the guards. You may need to deviate f
     8  Catch the rat in the north west room with your cat.
     9  Hide in the north east room until it's safe to go to the south east room, then catch the rats th
    10  Climb down the ladder.
    11  Catch the 3 rats down here.
    12  Talk to Jimmy Dazzler again.
    13  Talk to Hooknosed Jack in south east Varrock. You can give Jack your vial, kwuarm, and red spide
    14  Add rat poison to your cheese.
    15  Climb up the ladder south of Jack.
    16  Use a poisoned cheese on the rat holes.
    17  Return to Jack.
    18  Talk to the Apothecary in west Varrock.
    19  Talk to Jack again.
    20  Climb up the ladder south of Jack.
    21  Use your cat on the hole in the wall. You'll need to feed it by using fish ON THE WALL whenever
    23  Return to Jack.
    24  Travel to Keldagrim.
    25  Talk to Smokin' Joe in the north east of Keldagrim.
    26  Use the smouldering pot on the hole east of Joe with your cat following you and your catspeak am
    27  Use the smouldering pot on the rat hole again.
    28  Talk to Smokin' Joe again.
    29  Go down the manhole near The Face.
    30  Talk to Felkrash in the Port Sarim Rat Pits.
    31  Leave the rat pits.
    32  Talk to The Face in Port Sarim again.
    33  Use a coin on the pot next to the Snake Charmer in Pollnivneach.
    34  Return to just outside the Port Sarim Rat Pits.
    35  Click your snake charm and play it.
    36  Return to Felkrash to finish.

## Bank 119 -- Talk to Smokin%27 Joe & continue Ratcatchers until needing to go to Port Sarim[Ratcatchers]

    id: 0e33bfd18f        quest: ratcatchers

     0  Talk to Gertrude west of Varrock.
     1  Go down into Varrock Sewer via the Manhole south east of Varrock Castle.
     2  Talk to Phingspet in Varrock Sewer.
     3  Have your cat catch 8 rats.
     4  Talk to Phingspet in Varrock Sewer again.
     5  Talk to Jimmy Dazzler north of Ardougne Castle.
     6  Read the directions.
     7  Climb the trellis around the back of the mansion, avoiding the guards. You may need to deviate f
     8  Catch the rat in the north west room with your cat.
     9  Hide in the north east room until it's safe to go to the south east room, then catch the rats th
    10  Climb down the ladder.
    11  Catch the 3 rats down here.
    12  Talk to Jimmy Dazzler again.
    13  Talk to Hooknosed Jack in south east Varrock. You can give Jack your vial, kwuarm, and red spide
    14  Add rat poison to your cheese.
    15  Climb up the ladder south of Jack.
    16  Use a poisoned cheese on the rat holes.
    17  Return to Jack.
    18  Talk to the Apothecary in west Varrock.
    19  Talk to Jack again.
    20  Climb up the ladder south of Jack.
    21  Use your cat on the hole in the wall. You'll need to feed it by using fish ON THE WALL whenever
    23  Return to Jack.
    24  Travel to Keldagrim.
    25  Talk to Smokin' Joe in the north east of Keldagrim.
    26  Use the smouldering pot on the hole east of Joe with your cat following you and your catspeak am
    27  Use the smouldering pot on the rat hole again.
    28  Talk to Smokin' Joe again.
    29  Go down the manhole near The Face.
    30  Talk to Felkrash in the Port Sarim Rat Pits.
    31  Leave the rat pits.
    32  Talk to The Face in Port Sarim again.
    33  Use a coin on the pot next to the Snake Charmer in Pollnivneach.
    34  Return to just outside the Port Sarim Rat Pits.
    35  Click your snake charm and play it.
    36  Return to Felkrash to finish.

## Bank 124 -- Continue A Tail of Two Cats until after doing Unferth’s Chores (You have to wait 30 minutes to continue so leave after that)

    id: 939e85a9e6        quest: atailoftwocats

     0  Talk to Unferth in north east Burthorpe.
     1  Talk to Hild in the house north east of Unferth.
     2  Operate the catspeak amulet (e) to locate Bob the Cat. He's often in Catherby Archery Shop or at
     4  Talk to Gertrude west of Varrock.
     5  Talk to Reldo in the Varrock Castle's library.
     6  Use the catspeak amulet (e) again to locate Bob the Cat.
     8  Talk to the Sphinx in Sophanem.
     9  Rake Unferth's patch
    10  Plant 4 potato seeds in Unferth's patch. These can take 15-35 minutes to grow.
    11  Make Unferth's bed.
    12  Use logs on Unferth's fireplace
    13  Use a tinderbox on Unferth's fireplace.
    14  USE a chocolate cake on Unferth's table.
    15  Use a bucket of milk on Unferth's table.
    16  Use some shears on Unferth in north east Burthorpe.
    17  Talk to Unferth in north east Burthorpe again.
    18  Talk to the Apothecary in south west Varrock.
    19  Talk to Unferth whilst wearing the doctor/nurse hat, a desert shirt and a desert robe, and no we
    20  Use the catspeak amulet (e) to locate Bob once more.
    22  Talk to Unferth to complete the quest.

## Bank 145 -- Start Olaf's Quest until you get Sven's Last Map

    id: 824b6700a0        quest: olafsquest

     0  Talk to Olaf Hradson north east of Rellekka.
     1  Chop a log from the Windswept Tree east of Olaf.
     2  Bring the logs to Olaf Hradson north east of Rellekka.
     3  Talk to Ingrid Hradson near the well in southeast Rellekka.
     4  Talk to Volf Olafson north of the longhall in Rellekka.
     5  Return to Olaf Hradson north east of Rellekka.
     6  Use the damp planks on Olaf's embers.
     7  Talk to Olaf again, and give him some food.
     8  Dig next to the Windswept Tree.
     9  Go deeper into the caverns and kill a Skeleton Fremennik for a key.
    12  Pick up 2 rotten barrels and 6 ropes from around the room.
    13  WALK onto the walkway to the east, and use a barrel on it to repair it.
    14  WALK on the walkway and repair the next hole in it.
    15  Open the gate on the walkway, clicking the key hole which matches your key.
    16  WALK off the remaining walkway, and search the chest in the wreck. Be prepared to fight Ulfric.
    18  Search the chest again to finish the quest.

## Bank 153 -- Pickpocket Sandy until you get sand [Hand in the Sand]

    id: 9abb1168da        quest: thehandinthesand

     0  Talk to Bert in west Yanille.
     1  Give the Guard Captain in the pub south of Bert a beer. You can buy one for 2gp from the pub.
     2  Ring the bell outside the Wizards' Guild in Yanille. Talk to Zavistic Rarve when he appears.
     3  Return to Bert in west Yanille.
     4  Travel to Brimhaven, then enter Sandy's building south of the restaurant. Search Sandy's desk fo
     5  Pickpocket Sandy for some sand.
     6  Return to Bert in west Yanille with the rota and sand.
     7  Ring the bell outside the Wizards' Guild in Yanille. Talk to Zavistic Rarve when he appears.
     8  Talk to Zavistic Rarve again to get teleported to Port Sarim.
     9  Travel to Port Sarim, and talk to Betty in the magic shop.
    10  Use redberries on the bottled water.
    11  Use whiteberries on the red bottled water
    12  Use the pink dye on a lantern lens.
    13  Talk to Betty with the pink lens.
    14  Stand in Betty's doorway and use the rose-tinted lens on the counter.
    15  Talk to Betty again.
    16  Talk to Sandy in Brimhaven again with the truth serum. Select distractions until one works.
    17  Use the truth serum on Sandy's coffee mug.
    18  Activate the magical orb next to Sandy.
    19  Ask Sandy all questions available with the Magical orb (a) in your inventory.
    20  Return to the Wizards' Guild in Yanille and ring the bell outside. Talk to Zavistic Rarve when h
    21  Give Zavistic Rarve 5 earth runes and a bucket of sand.
    22  Travel to Entrana (bank all combat gear), and talk to Mazion at the sand pit.
    23  Return to the Wizards' Guild in Yanille and ring the bell outside. Talk to Zavistic Rarve when h

## Bank 160 -- Continue Mournings End Pt 1 until needing to go to Feldip Hills

    id: b6987fc352        quest: mourningsendparti

     0  Talk to Islwyn in Isafdar. If he's not at the marked location, try hopping worlds to find him he
     1  Talk to Arianwyn in Lletya.
     2  Kill a mourner travelling through the Arandar pass. This is more easily accessed from the north
     4  Search Tegid's laundry basket in south Taverley for some soap.
     6  Teleport to Lletya using a crystal teleport seed and talk to Oronwen to have them repair your tr
     7  Equip the full mourners outfit and enter the Mourners' Headquarters in West Ardougne.
     8  Go down the trapdoor in the north west corner of the HQ.
     9  Talk to Essyllt in the south room.
    10  Talk to the gnome on a rack.
    11  Use a feather on the gnome with toad crunchies in your inventory.
    12  Talk to the gnome again with the required items.
    13  Right-click release the gnome with the items.
    14  Give the gnome a magic log, some soft leather and some toad crunchies.
    15  Ask the gnome about ammo.
    16  You need to make some dyed toads. Go to Feldip Hills, use a dye on your empty bellows, then use
    18  Equip the full mourners outfit and enter the Mourners' Headquarters in West Ardougne.
    19  Go down the trapdoor in the north west corner of the HQ.
    20  Talk to Essyllt in the south room.
    21  Pick up a rotten apple from north-west of the Mourner HQ.
    22  Talk to Elena in north-west of East Ardougne.
    23  Pick up a barrel from the Orchard north of Ardougne.
    24  Use the barrel on a rotten apple pile.
    25  Use the rotten apples on the apple press.
    26  Make some Naphtha. Grab another barrel, fill it on the swamp south of the elven lands, then refi
    27  Use a barrel of naptha on the apple barrel.
    28  Use the sieve on the naphtha apple mix
    29  Cook the toxic naphtha on a range. DO NOT USE IT ON A FIRE, and MAKE SURE TO HAVE TWO FREE INVEN
    30  Use the toxic powder on the food store in the room north west of West Ardougne's town centre.
    31  Use the toxic powder on the food store in the church south of West Ardougne's town centre.
    32  Return to Essyllt in the Mourner HQ basement.
    33  Return to Arianwyn in Lletya.

## Bank 166 -- Continue In Search of Myreque until you kill the Hellhound

    id: b4fe127214        quest: insearchofthemyreque

     0  Talk to Vanstrom Klause in the Canifis pub.
     1  Fill a druid pouch with at least 5 Mort Myre items. Try to have more in case a ghast hits you.
     3  Board the swamp boaty in Mort'ton. If you forgot coins, you can obtain some by killing afflicted
     4  Climb the tree to the north of the boat.
     5  Repair the bridge.
     6  Talk to Curpile Fyod.
     7  Enter the wooden doors north of Curpile.
     8  Enter the cave to the north on the east side.
     9  Talk to Veliaf Hurtz.
    11  Talk to Veliaf Hurtz again and give him the steel weapons. Be ready to fight the Skeleton Hellho
    12  Kill the Skeleton Hellhound. To safespot the hellhound using Magic, position it on the south sid
    13  Talk to Veliaf Hurtz to learn the way out.
    14  Leave the cave.
    15  Leave up the ladder in the north of the cave.
    16  Talk to the Stranger in the Canifis pub to finish the quest!

## Bank 179 -- Continue At First Light until needing to go to Guild Hunter Fox

    id: 2ea2b97ff4        quest: atfirstlight

     0  Talk to Guildmaster Apatura in the Hunter Guild, south-west of Civitas illa Fortis.
     8  Go back up the stairs.
     9  Get a box trap. You can buy one from Imia in the north of the Hunter Guild's surface for 41gp.
    11  Search the leafy bush south of the crevice for a smooth leaf.
    12  Search the rough-looking bush on the west side of the Locus Oasis.
    16  Talk to Guild Hunter Fox.
    17  Talk to Atza in one of the buildings outside Civitas illa Fortis' south wall, west of the genera
    18  Take a hammer from the house north of Atza.
    20  Talk to Atza again for some trimmed fur.
    21  Return to Guild Hunter Fox near the crevice south-east of the Hunter Guild to get his report.
    26  Go back up the stairs and talk to Guildmaster Apatura to finish the quest.

## Bank 204 -- Continue At First Light until you need to head to Atza

    id: b8c1cff7b4        quest: atfirstlight

     0  Talk to Guildmaster Apatura in the Hunter Guild, south-west of Civitas illa Fortis.
     8  Go back up the stairs.
     9  Get a box trap. You can buy one from Imia in the north of the Hunter Guild's surface for 41gp.
    11  Search the leafy bush south of the crevice for a smooth leaf.
    12  Search the rough-looking bush on the west side of the Locus Oasis.
    16  Talk to Guild Hunter Fox.
    17  Talk to Atza in one of the buildings outside Civitas illa Fortis' south wall, west of the genera
    18  Take a hammer from the house north of Atza.
    20  Talk to Atza again for some trimmed fur.
    21  Return to Guild Hunter Fox near the crevice south-east of the Hunter Guild to get his report.
    26  Go back up the stairs and talk to Guildmaster Apatura to finish the quest.

## Bank 205 -- Once you get it, continue The Final Dawn until needing after killing the Emissary

    id: 596c86aa38        quest: thefinaldawn

     0  Talk to Servius in the Sunrise Palace in Civitas illa Fortis to start the quest.
     1  Search the chest in the south of the Tower of Ascension south of Salvager Overlook for some emis
     4  Enter the far eastern room. Avoid the patrolling guard.
     5  Search the bed in the south room.
     9  Enter the passage behind the painting.
    10  Picklock the chest in the hidden room. Be ready for a fight afterwards.
    11  Defeat the enforcer. You cannot use prayers. Step away each time he goes to attack, and step beh
    13  Read the emissary scroll.
    14  Talk to the queen on the top floor of the Sunrise Palace.
    15  Talk to Captain Vibia south of Civitas illa Fortis' west bank.
    16  Inspect the window on the east side of the house north of Captain Vibia, and then enter it.
    18  Pet the dog to see the code for the door. Open the door using the code 'GUS'.
    19  Pick up the sack of potatoes (3).
    28  Search Janus.
    29  Enter the basement in the hideout.
    30  Talk to the queen in the hideout basement.
    31  Enter Cam Torum.
    32  Talk to Attala in Cam Torum's marketplace.
    33  Talk to Servius in the house east of the bank in Cam Torum.
    38  Enter the house's basement.
    50  Inspect the fireplace.
    51  Enter the hole in the south-east corner of the room.
    52  Watch the cutscene with Ennius.
    53  Go back through the hole into the Teumo's basement.
    54  Talk to Servius in the house basement.
    55  Enter the Neypotzli entrance in the far north of the cavern.
    56  Talk to Eyatlalli.
    57  Enter the north-east entrance to the streambound cavern.
    58  Locate with the keystone fragment on the marked tile north of the cooking stove.
    66  Talk to Servius in Tal Teklan in the Tlati Rainforest, in the north-west of Varlamore. The easie
    67  Enter the passageway in the tree south-east of Tal Teklan, into the Crypt of Tonali.
    68  Defeat the attacking cultists.
    69  Defeat Ennius. Protect from Melee. Stand on the circles to avoid damage when they appear. Avoid
    70  Climb down the stairs.
    71  Step onto the red teleporter to the north-east.
    72  Step onto the blue teleporter to the west.
    73  Step on the red teleporter to the west.
    74  Step onto the blue teleporter to the north-west.
    75  Step on the red teleporter to the north.
    76  Climb the rope up to the north-east.
    77  Inspect the strange platform nearby to activate a shortcut lift from the surface.
    96  Enter the entrance in the north of the area.
    102  Talk to Prince Itzla Arkan to complete the quest!

## Bank 205 -- Continue The Final Dawn until needing to talk to Servius

    id: 508ae8e785        quest: thefinaldawn

     0  Talk to Servius in the Sunrise Palace in Civitas illa Fortis to start the quest.
     1  Search the chest in the south of the Tower of Ascension south of Salvager Overlook for some emis
     4  Enter the far eastern room. Avoid the patrolling guard.
     5  Search the bed in the south room.
     9  Enter the passage behind the painting.
    10  Picklock the chest in the hidden room. Be ready for a fight afterwards.
    11  Defeat the enforcer. You cannot use prayers. Step away each time he goes to attack, and step beh
    13  Read the emissary scroll.
    14  Talk to the queen on the top floor of the Sunrise Palace.
    15  Talk to Captain Vibia south of Civitas illa Fortis' west bank.
    16  Inspect the window on the east side of the house north of Captain Vibia, and then enter it.
    18  Pet the dog to see the code for the door. Open the door using the code 'GUS'.
    19  Pick up the sack of potatoes (3).
    28  Search Janus.
    29  Enter the basement in the hideout.
    30  Talk to the queen in the hideout basement.
    31  Enter Cam Torum.
    32  Talk to Attala in Cam Torum's marketplace.
    33  Talk to Servius in the house east of the bank in Cam Torum.
    38  Enter the house's basement.
    50  Inspect the fireplace.
    51  Enter the hole in the south-east corner of the room.
    52  Watch the cutscene with Ennius.
    53  Go back through the hole into the Teumo's basement.
    54  Talk to Servius in the house basement.
    55  Enter the Neypotzli entrance in the far north of the cavern.
    56  Talk to Eyatlalli.
    57  Enter the north-east entrance to the streambound cavern.
    58  Locate with the keystone fragment on the marked tile north of the cooking stove.
    66  Talk to Servius in Tal Teklan in the Tlati Rainforest, in the north-west of Varlamore. The easie
    67  Enter the passageway in the tree south-east of Tal Teklan, into the Crypt of Tonali.
    68  Defeat the attacking cultists.
    69  Defeat Ennius. Protect from Melee. Stand on the circles to avoid damage when they appear. Avoid
    70  Climb down the stairs.
    71  Step onto the red teleporter to the north-east.
    72  Step onto the blue teleporter to the west.
    73  Step on the red teleporter to the west.
    74  Step onto the blue teleporter to the north-west.
    75  Step on the red teleporter to the north.
    76  Climb the rope up to the north-east.
    77  Inspect the strange platform nearby to activate a shortcut lift from the surface.
    96  Enter the entrance in the north of the area.
    102  Talk to Prince Itzla Arkan to complete the quest!

## Bank 206 -- Continue The Final Dawn until you talk to Attala after killing Lucius & Chimalli

    id: c99b2bc33a        quest: thefinaldawn

     0  Talk to Servius in the Sunrise Palace in Civitas illa Fortis to start the quest.
     1  Search the chest in the south of the Tower of Ascension south of Salvager Overlook for some emis
     4  Enter the far eastern room. Avoid the patrolling guard.
     5  Search the bed in the south room.
     9  Enter the passage behind the painting.
    10  Picklock the chest in the hidden room. Be ready for a fight afterwards.
    11  Defeat the enforcer. You cannot use prayers. Step away each time he goes to attack, and step beh
    13  Read the emissary scroll.
    14  Talk to the queen on the top floor of the Sunrise Palace.
    15  Talk to Captain Vibia south of Civitas illa Fortis' west bank.
    16  Inspect the window on the east side of the house north of Captain Vibia, and then enter it.
    18  Pet the dog to see the code for the door. Open the door using the code 'GUS'.
    19  Pick up the sack of potatoes (3).
    28  Search Janus.
    29  Enter the basement in the hideout.
    30  Talk to the queen in the hideout basement.
    31  Enter Cam Torum.
    32  Talk to Attala in Cam Torum's marketplace.
    33  Talk to Servius in the house east of the bank in Cam Torum.
    38  Enter the house's basement.
    50  Inspect the fireplace.
    51  Enter the hole in the south-east corner of the room.
    52  Watch the cutscene with Ennius.
    53  Go back through the hole into the Teumo's basement.
    54  Talk to Servius in the house basement.
    55  Enter the Neypotzli entrance in the far north of the cavern.
    56  Talk to Eyatlalli.
    57  Enter the north-east entrance to the streambound cavern.
    58  Locate with the keystone fragment on the marked tile north of the cooking stove.
    66  Talk to Servius in Tal Teklan in the Tlati Rainforest, in the north-west of Varlamore. The easie
    67  Enter the passageway in the tree south-east of Tal Teklan, into the Crypt of Tonali.
    68  Defeat the attacking cultists.
    69  Defeat Ennius. Protect from Melee. Stand on the circles to avoid damage when they appear. Avoid
    70  Climb down the stairs.
    71  Step onto the red teleporter to the north-east.
    72  Step onto the blue teleporter to the west.
    73  Step on the red teleporter to the west.
    74  Step onto the blue teleporter to the north-west.
    75  Step on the red teleporter to the north.
    76  Climb the rope up to the north-east.
    77  Inspect the strange platform nearby to activate a shortcut lift from the surface.
    96  Enter the entrance in the north of the area.
    102  Talk to Prince Itzla Arkan to complete the quest!

## Bank ? -- Train on Sulpha Naguas until 60 Attack (If you ever want to AFK, the Naguas are vastly superior to most things as you also passively get RuneCrafting while crazy combat experience. Karambwans and Naguas should be your go to AFKs before Gem Crab/Shooting stars. It is advised to complete Perilous Moons before AFKing Naguas as you will get crazy rates with Dual Macahuitl’s and Bloodmoon.

    id: fa3409660f        quest: perilousmoon

     0  Talk to Attala, stood south of Ralos' Rise.
     1  Kill the sulphur nagua just atop the cliff north east of Attala. You can climb the rocks just to
     2  Return to Attala.
     3  Enter the entrance to Cam Torum.
     5  Enter the Neypotzli entrance in the far north of the cavern.
    20  Return to Cam Torum through the south entrance.
    21  Talk to Nahta in the magic shop.
    22  Talk to the blacksmith near the anvils.
    23  Enter the Neypotzli entrance in the far north of Cam Torum.
    26  Talk to Jessamine near the Monolith again.
    27  Enter the north-east entrance to the streambound cavern.
    28  Take herblore supplies from the supply crates in the camp. You only need the pestle and mortar.
    42  Enter the north-west entrance to the earthbound cavern when you're ready for the blue moon fight

## Bank ? -- Camp Perilous Moons until Eclipse & Blood (Green logging optional) [I don't recommend Birdhouse runs/Farm contracts while there]

    id: 0d73ecb105        quest: perilousmoon

     0  Talk to Attala, stood south of Ralos' Rise.
     1  Kill the sulphur nagua just atop the cliff north east of Attala. You can climb the rocks just to
     2  Return to Attala.
     3  Enter the entrance to Cam Torum.
     5  Enter the Neypotzli entrance in the far north of the cavern.
    20  Return to Cam Torum through the south entrance.
    21  Talk to Nahta in the magic shop.
    22  Talk to the blacksmith near the anvils.
    23  Enter the Neypotzli entrance in the far north of Cam Torum.
    26  Talk to Jessamine near the Monolith again.
    27  Enter the north-east entrance to the streambound cavern.
    28  Take herblore supplies from the supply crates in the camp. You only need the pestle and mortar.
    42  Enter the north-west entrance to the earthbound cavern when you're ready for the blue moon fight
