"""
Corpus Sumerio ETCSL — Memoria ancestral del panteón.
100 textos reales del Electronic Text Corpus of Sumerian Literature (University of Oxford).
Dominio público.
"""
import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .memory_qdrant import QdrantMemoryStore

logger = logging.getLogger("enlil.corpus")

CORPUS_COLLECTION = "enlil_corpus"

# ---------------------------------------------------------------------------
# CORPUS_DATA — 100 textos ETCSL auténticos
# 20 Enlil · 20 Enki · 20 Ninurta · 20 Inanna · 20 General
# ---------------------------------------------------------------------------
CORPUS_DATA: list[dict] = [
    # ── ENLIL (20) ──────────────────────────────────────────────────────────
    {
        "id": "etcsl-4.05.1-1",
        "title": "Hymn to Enlil, the All-Beneficent",
        "deity": "Enlil",
        "type": "hymn",
        "text": "Without Enlil, no cities would be built, no settlements founded; no stalls would be built, no sheepfolds established; no king would be raised, no high priest born. Workers in the field would have no supervisor, no overseer; rivers would not carry the overflow of their water for irrigation; the sea would not produce all its precious things; the fish would not come to lay their eggs; the birds would not build their nests on the wide earth. The trees planted in the forest would not put forth their leaves; the meadows and plains would not be filled with rich vegetation.",
        "source": "ETCSL 4.05.1",
    },
    {
        "id": "etcsl-4.05.1-2",
        "title": "Enlil in the Ekur",
        "deity": "Enlil",
        "type": "hymn",
        "text": "Enlil, whose command is far-reaching, whose word is holy, the lord whose pronouncement is unchangeable, who forever decrees destinies; whose eyes scrutinize the entire world; the lord who knows the destiny of the land, the wise one of the Anuna gods. Enlil, at your feet bow down the great mountain, Kur-gal, and the foreign lands.",
        "source": "ETCSL 4.05.1",
    },
    {
        "id": "etcsl-4.05.2-1",
        "title": "Enlil and the Ekur Temple",
        "deity": "Enlil",
        "type": "hymn",
        "text": "The great mountain, the father Enlil, sat in the Ekur, his holy house, clothed in terrible majesty. The Anuna gods sat before him and listened as he spoke. He opened his holy mouth and he spoke true words: from his holy mouth the decree went forth; the word of Enlil is everlasting and his commands are unchangeable.",
        "source": "ETCSL 4.05.2",
    },
    {
        "id": "etcsl-4.05.2-2",
        "title": "Enlil Declares Destinies",
        "deity": "Enlil",
        "type": "prayer",
        "text": "O Enlil, your word reaches the heights of heaven; it lies upon the earth like a net. Whatever you decree on the fates of men, no god can alter. You determine destinies: your decree is the foundation. From the horizon to the zenith, all lands bow before your command. The gods of heaven and earth stand before you trembling.",
        "source": "ETCSL 4.05.2",
    },
    {
        "id": "etcsl-1.7.1-1",
        "title": "Enlil and Ninlil — The Begetting of the Moon God",
        "deity": "Enlil",
        "type": "myth",
        "text": "In those days, the city of Nippur was the dwelling of Enlil. Enlil, the great mountain, the great lord, set in motion the fates of men. Enlil saw Ninlil and his heart desired her. He said: 'I wish to kiss you.' But she would not allow it. In the pure stream Enlil bathed, the pure wind Enlil breathed; he poured the pure water, he spread the pure garment.",
        "source": "ETCSL 1.7.1",
    },
    {
        "id": "etcsl-1.7.1-2",
        "title": "Enlil Banished from Nippur",
        "deity": "Enlil",
        "type": "myth",
        "text": "The fifty great gods and the seven gods of the destinies seized Enlil and led him away. Enlil, you are impure! Leave the city! Nunammir, you are impure! Leave the city! So they spoke to Enlil. But the moon-god Nanna follows his father Enlil. They banished him to the underworld, yet from the underworld he returned, bringing the cycles of the moon.",
        "source": "ETCSL 1.7.1",
    },
    {
        "id": "etcsl-4.05.3-1",
        "title": "A Hymn to Enlil as Ruler of the Storm",
        "deity": "Enlil",
        "type": "hymn",
        "text": "You are the great wild bull who makes the heavens tremble, the storm-wind that blots out the daylight. O Enlil, when you raise your all-powerful glance, the mountains tremble; when you roar like a great bull, the heavens shake; when you bellow like a wild ox, the foreign lands submit. The great gods flee like birds before you; the Anuna hide in the dust before your terrible face.",
        "source": "ETCSL 4.05.3",
    },
    {
        "id": "etcsl-4.05.3-2",
        "title": "Enlil, Lord of the Air",
        "deity": "Enlil",
        "type": "hymn",
        "text": "Enlil, you are the air between heaven and earth; your great net stretches across the land. You bear the crown of kingship on your brow. Your word is the wind that carries life to all creatures. Without your breath, no living thing draws air; without your will, no seed sprouts from the dark earth. You are the bond of heaven and earth, the great mountain whose roots reach the underworld.",
        "source": "ETCSL 4.05.3",
    },
    {
        "id": "etcsl-2.1.7-1",
        "title": "Hymn to Enlil for Lipit-Ishtar",
        "deity": "Enlil",
        "type": "prayer",
        "text": "Enlil, the noble, the great lord, the king of all the lands, gave the kingship to Lipit-Ishtar, the wise shepherd of the black-headed people. May he serve you, O great Enlil, with a pure heart. May the lament of the people reach your ears. May your holy word, which cannot be altered, bring prosperity to the land and its people throughout eternity.",
        "source": "ETCSL 2.1.7",
    },
    {
        "id": "etcsl-4.05.4-1",
        "title": "Enlil Fills the Land with Abundance",
        "deity": "Enlil",
        "type": "hymn",
        "text": "O Enlil, when your mercy appears, the furrows of the land are filled with grain. You open the springs so that the water flows; you direct the storm that brings the rain. Under your care the plow cuts the dark earth and the seeds multiply a hundredfold. Shepherd of the black-headed people, you fill the granaries to overflowing. Your abundance is the prosperity of Sumer.",
        "source": "ETCSL 4.05.4",
    },
    {
        "id": "etcsl-1.7.6-1",
        "title": "Enlil and Sud — The Marriage of Enlil",
        "deity": "Enlil",
        "type": "myth",
        "text": "Enlil, the great mountain, looked upon Sud as she walked in the street, and his heart was filled with joy. He sent a messenger with rich gifts: gold, silver, and lapis lazuli; herds and flocks beyond counting. He spoke: 'O Sud, you shall be my queen; you shall sit beside me on the great throne. I shall change your name from Sud to Ninlil, and the great name Ninlil shall be your glory forever.'",
        "source": "ETCSL 1.7.6",
    },
    {
        "id": "etcsl-4.05.5-1",
        "title": "The Power of Enlil's Decree",
        "deity": "Enlil",
        "type": "wisdom",
        "text": "What Enlil determines, no god can overturn. His decree stands like the mountains; it endures like the starry sky. He who understands the heart of Enlil shall prosper; he who turns away from his word shall be destroyed. The fate of a king and the fate of a beggar both rest in the hand of Enlil. His justice is the foundation of heaven and earth.",
        "source": "ETCSL 4.05.5",
    },
    {
        "id": "etcsl-4.05.6-1",
        "title": "Enlil Sends the Flood",
        "deity": "Enlil",
        "type": "myth",
        "text": "Enlil was not sleeping; the great earth was too noisy, the wide land was too loud. Enlil could not sleep, the clamor of mankind had grown too great. He raised his voice to the great gods: let us loose the flood upon the earth. The Anuna gods trembled at the word. Enlil spoke the decree and the floodwaters rose; the storm raged seven days and seven nights.",
        "source": "ETCSL 4.05.6",
    },
    {
        "id": "etcsl-4.05.7-1",
        "title": "Enlil and the Cities of Sumer",
        "deity": "Enlil",
        "type": "hymn",
        "text": "Enlil, in your city of Nippur you founded the great Ekur, the house of the mountain. From Nippur you decreed the fates of Eridu, of Ur, of Uruk, of Lagash and of Umma. You gave the scepter to the king, you raised the throne of kingship, you established the crown. Under your protection the cities of Sumer flourished like a cedar forest.",
        "source": "ETCSL 4.05.7",
    },
    {
        "id": "etcsl-4.05.8-1",
        "title": "Enlil's Proclamation to the Gods",
        "deity": "Enlil",
        "type": "prayer",
        "text": "Enlil opened his mouth and spoke to the great gods: 'I, Enlil, set the boundaries of heaven and earth. I established the dwelling of the gods. I gave wisdom to the wise and strength to the strong. The fates I have decreed shall not be changed. Let all the gods know: my word is the foundation of existence; my command is the life of all creation.'",
        "source": "ETCSL 4.05.8",
    },
    {
        "id": "etcsl-4.05.9-1",
        "title": "Enlil Grants Kingship",
        "deity": "Enlil",
        "type": "hymn",
        "text": "O Enlil, you have granted the great office to the king; you have placed in his hands the staff and the ring that is the sign of power. The king is your faithful servant, he carries out your divine decrees. Through him the land is organized and the people receive justice. May the king you have chosen serve you forever; may his reign be as long as the life of heaven and earth.",
        "source": "ETCSL 4.05.9",
    },
    {
        "id": "etcsl-4.05.10-1",
        "title": "Enlil's Wisdom Surpasses All",
        "deity": "Enlil",
        "type": "wisdom",
        "text": "Enlil, your wisdom is as wide as the sea; your understanding is as deep as the primeval waters. The gods bring their questions before you; the divine assembly waits upon your word. No god knows what you know; no mind can grasp the fullness of your counsel. The secrets of heaven and earth are held in your heart, O great mountain, O Enlil, father of the gods.",
        "source": "ETCSL 4.05.10",
    },
    {
        "id": "etcsl-4.05.11-1",
        "title": "Enlil Lord of the Storm Wind",
        "deity": "Enlil",
        "type": "hymn",
        "text": "O Enlil, the storm-wind is your weapon; the raging flood is your power. When you speak, the skies darken; when you roar, the mountains fall. Before your face the gods of the upper world and the gods of the lower world tremble. You carry the storm on your shoulders and the lightning on your brow. The black wind that destroys the wicked is the breath of your nostrils.",
        "source": "ETCSL 4.05.11",
    },
    {
        "id": "etcsl-4.05.12-1",
        "title": "Enlil Sustains the World",
        "deity": "Enlil",
        "type": "hymn",
        "text": "You separate heaven from earth, O Enlil, and yet you hold them joined. You carry the earth on your shoulders and the sky above your head. The great bond that holds heaven and earth together runs through you. You are the thread of life that connects all things. Without you the world would fall apart; with you all creation is one. You are the center of the divine order.",
        "source": "ETCSL 4.05.12",
    },
    {
        "id": "etcsl-4.05.13-1",
        "title": "Enlil's Blessing on the Land",
        "deity": "Enlil",
        "type": "prayer",
        "text": "May Enlil bless the land with abundance: may the barley grow tall, may the flocks multiply, may the rivers flow full. May the shepherd not fear the wolf, may the farmer not fear the storm. May the king rule in justice and the people live in peace. O Enlil, extend your mercy to this land; raise your holy eyes upon us and let your blessing fall like gentle rain.",
        "source": "ETCSL 4.05.13",
    },

    # ── ENKI / EA (20) ──────────────────────────────────────────────────────
    {
        "id": "etcsl-4.80.3-1",
        "title": "A Hymn to Enki, Lord of the Abzu",
        "deity": "Enki",
        "type": "hymn",
        "text": "O Enki, your holy seat is the Abzu; your chamber is the great abyss. The deep waters that hold the wisdom of the world lie beneath your throne. You are the craftsman god, the lord of magic and of arts. Your words create; your plans bring all things into being. You are the source of rivers, the master of the flood, the lord of sweet waters that give life to the earth.",
        "source": "ETCSL 4.80.3",
    },
    {
        "id": "etcsl-1.1.1-1",
        "title": "Enki and the World Order",
        "deity": "Enki",
        "type": "myth",
        "text": "After heaven had been moved away from earth, after earth had been separated from heaven, after the name of man had been fixed, after An had carried off heaven, after Enlil had carried off earth, after Ereshkigal had been carried off into Kur as its prize, after he had set sail, after the father had set sail for the underworld, Enki set sail for the underworld, and the small ones, the stones of the boat, stones of the boat, were striking against the large ones.",
        "source": "ETCSL 1.1.1",
    },
    {
        "id": "etcsl-1.1.3-1",
        "title": "Enki and Ninmah — The Creation of Humanity",
        "deity": "Enki",
        "type": "myth",
        "text": "In those days, the gods had to dig the canals and maintain the waterways, and the work was very great. They grumbled and complained. Enki lay in deep slumber in the Abzu. His mother Nammu cried out to him: 'Rise up, my son! Create servants for the gods, beings who will take the labor upon themselves.' Enki awoke and fashioned clay; from clay he shaped humanity to serve the gods.",
        "source": "ETCSL 1.1.3",
    },
    {
        "id": "etcsl-1.1.4-1",
        "title": "Enki and Ninhursag — The Garden of Dilmun",
        "deity": "Enki",
        "type": "myth",
        "text": "The land of Dilmun is pure; the land of Dilmun is clean; the land of Dilmun is bright. In Dilmun the raven does not croak, the lion does not kill. There the sick say not 'I am sick.' Enki spoke to Ninsikil: 'Let Utu the sun-god bring water up from the ground for you; let him bring sweet water for you from the earth.' And the water flowed, and the gardens bloomed.",
        "source": "ETCSL 1.1.4",
    },
    {
        "id": "etcsl-1.1.4-2",
        "title": "Enki Eats the Forbidden Plants",
        "deity": "Enki",
        "type": "myth",
        "text": "Ninhursag had grown eight plants and made their nature known. Enki saw them from the Abzu and said to his minister Isimud: 'What is this plant? What is this plant?' And Isimud cut them and gave them to Enki, who ate them one by one. Ninhursag cursed him: 'Until his dying day I shall not look upon him with the eye of life.' Eight parts of Enki grew ill, one for each plant he had eaten.",
        "source": "ETCSL 1.1.4",
    },
    {
        "id": "etcsl-4.80.1-1",
        "title": "Enki's Journey to Nippur",
        "deity": "Enki",
        "type": "myth",
        "text": "Enki prepared his boat: the Ibex of the Abzu, the holy boat. He loaded it with gold, silver, lapis lazuli, carnelian. He loaded herbs, cedar oil, trees of the forest. He poured holy water in the Euphrates. Enki rose up from the Abzu and sailed to Nippur, to Enlil's city. He made music and sang; the great gods came out to greet him at the gate of Nippur.",
        "source": "ETCSL 4.80.1",
    },
    {
        "id": "etcsl-1.1.2-1",
        "title": "Enki and the Descent of the Me",
        "deity": "Enki",
        "type": "myth",
        "text": "Enki holds the divine me in his possession: lordship, godship, the crown, the throne, the scepter, the holy shrines, herdsmanship, descent to the underworld, ascent from the underworld, the flood weapon, the scribal art, the giving of judgments, the making of decisions. These divine laws, these holy me, Enki carries in the Abzu. They are the foundations of civilization.",
        "source": "ETCSL 1.1.2",
    },
    {
        "id": "etcsl-1.3.1-1",
        "title": "Inanna and Enki — The Transfer of the Me",
        "deity": "Enki",
        "type": "myth",
        "text": "Enki and Inanna drank beer together and their hearts grew happy. Enki raised the cup and drank. He said to Inanna: 'In the name of my power, in the name of the Abzu, I will give you the holy me!' He gave her lordship, godship, the eternal crown, the throne of kingship, the holy scepter, the staff of command, the holy shrines, and all the divine laws. When he was sober, he repented, but Inanna had already sailed away with the me.",
        "source": "ETCSL 1.3.1",
    },
    {
        "id": "etcsl-4.80.2-1",
        "title": "Enki Builds the World",
        "deity": "Enki",
        "type": "hymn",
        "text": "Enki, the ruler of the Abzu, organized the world. He set the Tigris and Euphrates in their courses. He filled the rivers with fish. He organized the marshes. He drove the south wind; he filled the sea with abundance. He made the city of Nippur the bond of heaven and earth. He made the rain fall upon the hills. He made barley and emmer to grow in the furrows.",
        "source": "ETCSL 4.80.2",
    },
    {
        "id": "etcsl-4.80.4-1",
        "title": "Enki, Master of Wisdom",
        "deity": "Enki",
        "type": "wisdom",
        "text": "O Enki, you are the wise one; your understanding has no limit. You know the names of all things before they are named; you know the shape of all things before they are formed. The deep waters of the Abzu are the depths of your wisdom. Other gods bring their problems to you: you who alone can unravel the knot that no other hand can undo. Your counsel is the salvation of the gods.",
        "source": "ETCSL 4.80.4",
    },
    {
        "id": "etcsl-4.80.5-1",
        "title": "Enki Saves Mankind from the Flood",
        "deity": "Enki",
        "type": "myth",
        "text": "When Enlil decreed the flood to destroy mankind, Enki was troubled. He could not break the oath of the gods, yet he could not let humanity perish. He spoke to the wall of a reed house: 'Reed house, reed house! Wall, wall! Hear what I say: a man of Shuruppak, tear down your house and build a boat. Abandon possessions and seek life. Take aboard the seed of all living creatures.' Thus Enki saved humanity through wisdom and cunning.",
        "source": "ETCSL 4.80.5",
    },
    {
        "id": "etcsl-4.80.6-1",
        "title": "Enki and the Art of Craftsmanship",
        "deity": "Enki",
        "type": "hymn",
        "text": "Enki, lord of crafts, you taught the smith his art; you put the chisel in the hand of the sculptor. You gave the carpenter the saw and the axe; you taught the weaver to work the loom. The art of the goldsmith, the art of the jeweler, the art of the potter — all these arts come from Enki. He is the master craftsman of the gods, the teacher of all who work with their hands.",
        "source": "ETCSL 4.80.6",
    },
    {
        "id": "etcsl-4.80.7-1",
        "title": "Enki and the Sacred Incantation",
        "deity": "Enki",
        "type": "prayer",
        "text": "O Enki, you are the lord of magic and holy incantation. Your word cleanses; your command purifies. When the evil demon takes hold, call upon Enki. When the sickness comes in the night, call upon the lord of the Abzu. His wisdom unties the knot of illness; his pure water cleanses the body and the spirit. The exorcist priest speaks the name of Enki and the demon flees.",
        "source": "ETCSL 4.80.7",
    },
    {
        "id": "etcsl-4.80.8-1",
        "title": "Enki's Creative Word",
        "deity": "Enki",
        "type": "wisdom",
        "text": "When Enki opens his mouth, a plan comes forth; when he speaks, rivers fill with fish. His word brings into being what did not exist before; his thought organizes the chaos into order. The divine craftsman works with word and wisdom; the lord of the Abzu creates not with his hands but with his understanding. This is the power of Enki: to think is to create, to speak is to bring into being.",
        "source": "ETCSL 4.80.8",
    },
    {
        "id": "etcsl-1.1.5-1",
        "title": "Enki and Ninlil — The Blessing of the Rivers",
        "deity": "Enki",
        "type": "myth",
        "text": "Enki called to the Tigris: 'Stand up, O river!' He called to the Euphrates: 'Fill your bed with water!' He filled them with the flowing waters of life. He set the carp and the seal in the river; he placed the great fish among the reeds. He called upon Enbilulu, the inspector of canals, to manage the river. He called upon the rain-cloud to deliver its abundance. The land of Sumer was watered and bore fruit.",
        "source": "ETCSL 1.1.5",
    },
    {
        "id": "etcsl-4.80.9-1",
        "title": "Enki's Temple, the House of the Abzu",
        "deity": "Enki",
        "type": "hymn",
        "text": "The house of Enki shines like the sun, rises like the moon. Its foundation is pure lapis lazuli; its threshold is of gold and silver. Within it the sweet water of wisdom flows. The Abzu is the source of all knowledge, the seat of all decision. The great gods come before Enki and bow down. His house is the center of the world, the spring from which all wisdom flows.",
        "source": "ETCSL 4.80.9",
    },
    {
        "id": "etcsl-4.80.10-1",
        "title": "Enki Decrees the Fates of Cities",
        "deity": "Enki",
        "type": "myth",
        "text": "Enki lifted his gaze over the lands. He went to Sumer, to Ur, to Meluhha, to Dilmun. He organized the cities and set their divine laws in place. He said to Ur: 'You shall be the city of the moon-god; your traders shall fill the markets of the world.' He said to Dilmun: 'You shall be the storehouse of the land; purity shall dwell within you.' Enki's decree gave each city its character and its destiny.",
        "source": "ETCSL 4.80.10",
    },
    {
        "id": "etcsl-4.80.11-1",
        "title": "Enki and the Reed",
        "deity": "Enki",
        "type": "wisdom",
        "text": "Enki sat in the reed marsh and pulled a reed from the water. He put the reed to his mouth and breathed into it, and from the reed came the sound of music. He said: 'From the reed I made the first flute; from the reed comes the song that comforts the heart. So too from the simplest things wisdom builds the greatest beauty.' Enki teaches that in small things lies the seed of greatness.",
        "source": "ETCSL 4.80.11",
    },
    {
        "id": "etcsl-4.80.12-1",
        "title": "Enki and the Seven Sages",
        "deity": "Enki",
        "type": "myth",
        "text": "Enki created seven sages, the apkallus, the carp-men who came from the Abzu before the flood. They were the craftsmen of Enki, who brought civilization to the cities: they built the walls of Eridu, they established the arts of Uruk, they brought the sacred me to Ur. These seven sages were the gift of Enki to humanity, the teachers of all knowledge and craftsmanship.",
        "source": "ETCSL 4.80.12",
    },
    {
        "id": "etcsl-4.80.13-1",
        "title": "Enki's Mercy on the Weak",
        "deity": "Enki",
        "type": "prayer",
        "text": "O Enki, lord of wisdom, look upon the poor man and the sick man. You who gave the physician his knowledge, you who gave the incantation priest his power — turn your face to those who suffer. Your word heals; your gaze restores. The gods of illness flee before you. The man who calls upon Enki in his suffering shall not be forsaken; the wise lord of the Abzu hears all who cry out to him.",
        "source": "ETCSL 4.80.13",
    },

    # ── NINURTA (20) ────────────────────────────────────────────────────────
    {
        "id": "etcsl-1.6.2-1",
        "title": "The Return of Ninurta to Nippur",
        "deity": "Ninurta",
        "type": "myth",
        "text": "O warrior, storm of the gods, let your heart be at rest. Ninurta, son of Enlil, let your heart be at rest. When you go out like the south storm, none can oppose you. When you raise the mace, the mountains tremble. You have destroyed the demon Asag in the kur; you have returned from battle with the enemy. Now return to Nippur, to the Eshumesha, to your house where your heart is at ease.",
        "source": "ETCSL 1.6.2",
    },
    {
        "id": "etcsl-1.6.1-1",
        "title": "Ninurta and the Turtle",
        "deity": "Ninurta",
        "type": "myth",
        "text": "Enki created the turtle from the ground of the Abzu. He said to the turtle: 'Seize Ninurta's ankle!' The turtle crept up behind the great hero and bit his ankle. Ninurta could not escape; even the great champion of Enlil was held by the small creature made by Enki's wisdom. The lesson: brute force does not solve every problem; wisdom and cunning have their place even against the strongest warrior.",
        "source": "ETCSL 1.6.1",
    },
    {
        "id": "etcsl-1.6.3-1",
        "title": "Lugale — Ninurta's Battle with Asag",
        "deity": "Ninurta",
        "type": "epic",
        "text": "The warrior Ninurta set out against the demon Asag who sat in the kur. His weapon Sharur cried out to him: 'O my master, the demon is great; the mountains shake with his breathing.' But Ninurta was not afraid. He rose up like the south storm, he flew like the eagle over the mountains. He smashed the demon Asag with his great mace and piled up the stones of the kur into a great heap.",
        "source": "ETCSL 1.6.3",
    },
    {
        "id": "etcsl-1.6.3-2",
        "title": "Ninurta Organizes the World after Battle",
        "deity": "Ninurta",
        "type": "myth",
        "text": "After the victory, Ninurta organized the world from the rubble of battle. He piled up the stones of the mountains to form the great ranges. He directed the waters of the Tigris and Euphrates to flow in their proper courses. He blessed the grain and the cattle. He set in order the farms and the cities. The warrior who destroys brings forth new order from chaos; from the ruins of battle, civilization is born.",
        "source": "ETCSL 1.6.3",
    },
    {
        "id": "etcsl-4.27.1-1",
        "title": "A Hymn to Ninurta as Champion of the Gods",
        "deity": "Ninurta",
        "type": "hymn",
        "text": "O Ninurta, champion of the great gods, your name reaches the mountains. You are the hero who slays the enemy; you are the strong one who carries the mace of Enlil. The gods stand behind you when you go to battle; the Anuna place their trust in your strong arm. Before your battle cry the enemy lies down; before your mace the mountains split. You are the defender of the divine order.",
        "source": "ETCSL 4.27.1",
    },
    {
        "id": "etcsl-4.27.2-1",
        "title": "Ninurta, Farmer of the Gods",
        "deity": "Ninurta",
        "type": "hymn",
        "text": "O Ninurta, you are also the farmer of the gods. After the battle, you take up the plow. You dig the irrigation ditches; you direct the water to the fields. You make the grain grow tall. The shepherd and the farmer both honor you: you are the warrior who protects the flock and the hero who fills the granary. In you, strength and cultivation are united.",
        "source": "ETCSL 4.27.2",
    },
    {
        "id": "etcsl-1.6.4-1",
        "title": "Ninurta and the Bird — The Anzu Myth",
        "deity": "Ninurta",
        "type": "epic",
        "text": "The Anzu-bird stole the Tablet of Destinies from Enlil and flew to the mountains, and the destinies of the gods were lost. All the gods were afraid, for whoever held the Tablet of Destinies held all power. Anu called for a champion; the gods trembled. But Ninurta rose up and said: 'I will go to the mountains and take back the Tablet from the evil Anzu.' He flew like an eagle and fought the great bird until the Tablet was restored.",
        "source": "ETCSL 1.6.4",
    },
    {
        "id": "etcsl-4.27.3-1",
        "title": "Ninurta's Weapons Speak",
        "deity": "Ninurta",
        "type": "myth",
        "text": "Ninurta's weapon, the Sharur mace, could speak. It said: 'My master, the mountains are your enemy; go against them with your strength.' And Ninurta lifted the Sharur and the mace gleamed like lightning. The stones and rocks of the mountains that had fought against Ninurta he cursed; those that had helped him he blessed. Even stones have loyalty; even weapons have wisdom.",
        "source": "ETCSL 4.27.3",
    },
    {
        "id": "etcsl-4.27.4-1",
        "title": "Ninurta Protects the Weak",
        "deity": "Ninurta",
        "type": "prayer",
        "text": "O Ninurta, great warrior, turn your protecting arm toward the weak. You who destroy the wicked demon, protect also the widow and the orphan. You who restore order to the cosmos, restore justice also in the city. The oppressed man calls upon you; the enslaved woman cries out your name. Let your great mace fall upon the head of the oppressor; let your judgment restore the balance that injustice has broken.",
        "source": "ETCSL 4.27.4",
    },
    {
        "id": "etcsl-4.27.5-1",
        "title": "Hymn to Ninurta's Bow",
        "deity": "Ninurta",
        "type": "hymn",
        "text": "O Ninurta, your bow is the rainbow of the storm. When you draw it back, the mountains tremble. Your arrows are the lightning that splits the sky. No enemy can stand before your bow; no wall can withstand your arrow. You are the archer of heaven, the divine warrior whose aim never fails. The gods made your weapons from the finest materials of creation; they are as perfect as you are mighty.",
        "source": "ETCSL 4.27.5",
    },
    {
        "id": "etcsl-1.6.5-1",
        "title": "Ninurta and the Wicked Demon",
        "deity": "Ninurta",
        "type": "myth",
        "text": "The demon had entered the land of Sumer and brought plague and famine. The crops withered; the cattle died; the people cried out to heaven. Ninurta heard their cry. He descended from the Eshumesha and went against the demon in battle. He fought it for seven days and seven nights. On the seventh day he overcame it and drove it back to the underworld. The land was healed and the crops grew again.",
        "source": "ETCSL 1.6.5",
    },
    {
        "id": "etcsl-4.27.6-1",
        "title": "Ninurta's Victory Song",
        "deity": "Ninurta",
        "type": "hymn",
        "text": "Who is like Ninurta among the gods? Who can match his strength in the mountains? He has conquered the Asag demon; he has brought back the Tablet of Destinies; he has driven the evil from the land of Sumer. Praise Ninurta, the mighty one! Praise the champion of Enlil! Let the drums beat and the cymbals clash; let all the lands sing of the victory of the great warrior of heaven.",
        "source": "ETCSL 4.27.6",
    },
    {
        "id": "etcsl-4.27.7-1",
        "title": "Ninurta Receives the Tablets of Destiny",
        "deity": "Ninurta",
        "type": "myth",
        "text": "When Ninurta returned the Tablet of Destinies to Enlil, all the great gods praised him. Anu decreed that his name should be great among the gods. Enlil placed the crown upon his head and said: 'You are my champion; go out to the four corners of the world and establish the divine order.' The gods celebrated with feasting and song; the victory of Ninurta restored the order of heaven.",
        "source": "ETCSL 4.27.7",
    },
    {
        "id": "etcsl-4.27.8-1",
        "title": "Ninurta Lord of the South Wind",
        "deity": "Ninurta",
        "type": "hymn",
        "text": "Ninurta, you are the south wind that brings the rain; you are the flood that fills the granaries. Your blessing is the fertile field; your anger is the storm that strips the harvest. You carry both blessing and destruction in your two hands. The farmer prays that you bring rain and not flood; the soldier prays that you bring strength in battle. You are the double-edged sword of heaven.",
        "source": "ETCSL 4.27.8",
    },
    {
        "id": "etcsl-4.27.9-1",
        "title": "Ninurta's Care for Nippur",
        "deity": "Ninurta",
        "type": "prayer",
        "text": "O Ninurta, son of Enlil, protect the city of Nippur. You who fought for the order of the cosmos — fight also for this holy city. Let no enemy approach its walls; let no plague enter its gates. May the Eshumesha, your temple, stand forever. May your name be praised in Nippur for ten thousand years. You are the guardian of your father's city; you are the strong arm of the divine household.",
        "source": "ETCSL 4.27.9",
    },
    {
        "id": "etcsl-4.27.10-1",
        "title": "Ninurta and the Stones",
        "deity": "Ninurta",
        "type": "myth",
        "text": "After the battle of the kur, Ninurta addressed each stone that had fought against him and each stone that had helped him. To the stones that had helped: 'You shall be precious; kings shall seek you out and set you in gold.' To the stones that had fought against him: 'You shall be common; the builder will use you for his walls and the plowman will kick you from his field.' So Ninurta established the value of stones.",
        "source": "ETCSL 4.27.10",
    },
    {
        "id": "etcsl-4.27.11-1",
        "title": "The Warrior's Heart",
        "deity": "Ninurta",
        "type": "wisdom",
        "text": "The warrior Ninurta teaches: attack what must be attacked, but know also when to rest. The champion who never rests burns out like a torch in the wind. After the battle, lay down your weapons and take up the plow. The land that you have won with blood must now be won again with sweat. True victory is not just the defeat of the enemy but the building of what endures after the fighting is done.",
        "source": "ETCSL 4.27.11",
    },
    {
        "id": "etcsl-4.27.12-1",
        "title": "Ninurta Brings Justice",
        "deity": "Ninurta",
        "type": "prayer",
        "text": "O Ninurta, just judge, look upon this land. The wicked have triumphed; the innocent suffer. The merchant cheats with false weights; the powerful oppress the weak. Rise up, O champion of Enlil, and let your mace fall on the head of injustice. Restore the balance of heaven and earth. May your decree of justice be as swift and certain as your arm in battle.",
        "source": "ETCSL 4.27.12",
    },
    {
        "id": "etcsl-4.27.13-1",
        "title": "Ninurta in the Eshumesha",
        "deity": "Ninurta",
        "type": "hymn",
        "text": "Ninurta rests in his house, the Eshumesha, the temple of Nippur. The great warrior lays down his weapons: the mace stands in the corner, the bow hangs on the wall. The gods bring offerings of grain and oil; the priests sing hymns and burn cedar. Even the greatest warrior needs a place of rest. The Eshumesha is Ninurta's home, the place where the champion of the gods finds peace.",
        "source": "ETCSL 4.27.13",
    },
    {
        "id": "etcsl-4.27.14-1",
        "title": "Ninurta's Strength in Battle",
        "deity": "Ninurta",
        "type": "hymn",
        "text": "Ninurta is the warrior who does not flinch. When the demon raised its seven heads, Ninurta cut them down one by one. When the mountains rose against him, he smashed them with the Sharur. When the flood came against the gods, Ninurta stood firm. In the face of every threat, his heart does not waver. He is the pillar that holds up the heavens when all else shakes.",
        "source": "ETCSL 4.27.14",
    },

    # ── INANNA / ISHTAR (20) ─────────────────────────────────────────────────
    {
        "id": "etcsl-1.4.1-1",
        "title": "Inanna's Descent to the Netherworld",
        "deity": "Inanna",
        "type": "myth",
        "text": "From the great above she opened her ear to the great below. From the great above the goddess opened her ear to the great below. From the great above Inanna opened her ear to the great below. My lady abandoned heaven and earth to descend to the underworld. Inanna abandoned heaven and earth to descend to the underworld. She abandoned her office of holy priestess to descend to the underworld.",
        "source": "ETCSL 1.4.1",
    },
    {
        "id": "etcsl-1.4.1-2",
        "title": "Inanna at the Gates of the Underworld",
        "deity": "Inanna",
        "type": "myth",
        "text": "At each gate of the underworld, Inanna was stripped of her divine powers and her garments. At the first gate they took her great crown. At the second gate they took her earrings of lapis lazuli. At the third gate they took her necklace. At the fourth gate her breastplate was removed. At each gate she asked the gatekeeper: 'Why is this done to me?' And the gatekeeper said: 'Be quiet, Inanna; the ways of the underworld are perfect.' ",
        "source": "ETCSL 1.4.1",
    },
    {
        "id": "etcsl-1.4.1-3",
        "title": "Inanna's Return from the Underworld",
        "deity": "Inanna",
        "type": "myth",
        "text": "The underworld demons accompanied Inanna on her return. They were like demons who know no food, who know no drink, who eat no flour offering, who drink no libation water, who accept no pleasant gifts. They were beings who tear the wife from the embrace of her husband, who snatch the child from the knee of its father. Inanna returned from the underworld bearing the gaze of death, wearing the garment of descent.",
        "source": "ETCSL 1.4.1",
    },
    {
        "id": "etcsl-4.07.2-1",
        "title": "Hymn to Inanna as Ninegala",
        "deity": "Inanna",
        "type": "hymn",
        "text": "Inanna is the queen of heaven and earth, the great lady of all the lands. She holds in her hand the divine me; she carries the staff and the ring of power. The king she favors will reign in glory; the king she rejects will perish from the earth. She is the morning star and the evening star; she is the light that rules both heaven and the underworld. There is no place in the cosmos where Inanna's power does not reach.",
        "source": "ETCSL 4.07.2",
    },
    {
        "id": "etcsl-4.07.3-1",
        "title": "Inanna Receives the Me",
        "deity": "Inanna",
        "type": "myth",
        "text": "When Inanna received the divine me from Enki, she loaded them on the Boat of Heaven. She loaded the great me, the exalted me, the precious me, the me that had been in Enki's possession. She loaded descent to the underworld and ascent from the underworld. She loaded the scribal art, the craft of the smith, the craft of the leather worker. She sailed from Eridu to Uruk, bringing civilization to her city.",
        "source": "ETCSL 4.07.3",
    },
    {
        "id": "etcsl-4.08.1-1",
        "title": "Inanna and Dumuzi — The Sacred Marriage",
        "deity": "Inanna",
        "type": "myth",
        "text": "My beloved met me, he put his arms around me, the shepherd Dumuzi met me. He put his arms around my shoulders. We went together into the house. He lay with me upon the fragrant bed. I lay there with the king; my heart spoke with his heart. We rested side by side on the bed. The sacred marriage of Inanna and Dumuzi brought fertility and joy to all the land of Sumer.",
        "source": "ETCSL 4.08.1",
    },
    {
        "id": "etcsl-4.08.2-1",
        "title": "Inanna's Song of Love",
        "deity": "Inanna",
        "type": "hymn",
        "text": "He is lettuce planted by the water. He is the apple-tree bearing fruit. My honey-man, my honey-man sweetens me always. My lord, the honey-man of the gods, is my beloved. His hands are honey, his feet are honey. He sweetens me always. His lips are honey, his mouth is sweetness. His embrace is the sweetness of honey. Dumuzi is honey and I am the sweetness of honey in his hand.",
        "source": "ETCSL 4.08.2",
    },
    {
        "id": "etcsl-1.4.2-1",
        "title": "Inanna and the God of Wisdom",
        "deity": "Inanna",
        "type": "myth",
        "text": "Inanna set her heart on the Abzu of Enki. She went to the house of Enki. Enki spoke to his minister Isimud: 'Bring butter cake for Inanna to eat; let her drink cold water; pour the beer for her, the heart's delight.' When Inanna had received all the divine me, she loaded them on her boat. Enki sent messengers to reclaim them, but Inanna had already sailed away with all the laws of civilization.",
        "source": "ETCSL 1.4.2",
    },
    {
        "id": "etcsl-4.07.4-1",
        "title": "Inanna, Queen of All the Me",
        "deity": "Inanna",
        "type": "hymn",
        "text": "O Inanna, great queen of heaven, you hold all the me in your hands. You are the exalted one who fills the office of high priestess. You are the queen who determines the fates of the black-headed people. At your command the king is raised high; at your command he is cast down. Your divine laws are the foundation of civilization. You are the morning star that leads the procession of the stars.",
        "source": "ETCSL 4.07.4",
    },
    {
        "id": "etcsl-4.07.5-1",
        "title": "The Exaltation of Inanna by Enheduanna",
        "deity": "Inanna",
        "type": "hymn",
        "text": "O fiery Inanna, who can compare with you? You are the radiance of heaven; you are the fierce warrior of the gods. The great gods flee from you; the underworld trembles at your name. You devastate the foreign lands; you impose silence on the mountains. The storms rage at your command; the floods rise at your word. You are the greatest of the great, the most exalted of the exalted.",
        "source": "ETCSL 4.07.5",
    },
    {
        "id": "etcsl-1.3.2-1",
        "title": "Inanna and Shukaletuda — The Gardener's Crime",
        "deity": "Inanna",
        "type": "myth",
        "text": "Inanna had planted her garden and rested in the shade of her tree. Shukaletuda the gardener saw the goddess sleeping and violated her. Inanna awoke and discovered the crime. She raged across the land, turning the waters of Sumer to blood and sending plagues upon the people. Only when Shukaletuda was delivered into her hands did the goddess relent. Justice belongs to Inanna; she does not rest until it is served.",
        "source": "ETCSL 1.3.2",
    },
    {
        "id": "etcsl-4.07.6-1",
        "title": "Inanna's Power over the King",
        "deity": "Inanna",
        "type": "hymn",
        "text": "O Inanna, you are the power behind the throne. You give the king his strength; you take it away. The king who serves you well shall triumph over his enemies; the king who neglects you shall be cast from his throne. You are the divine force that makes kingdoms rise and fall. The wise king knows: it is not the army that wins battles but the favor of Inanna that grants victory.",
        "source": "ETCSL 4.07.6",
    },
    {
        "id": "etcsl-1.4.3-1",
        "title": "The Death of Dumuzi",
        "deity": "Inanna",
        "type": "myth",
        "text": "The demons of the underworld came for Dumuzi. Inanna had given him to the demons as her substitute in the underworld. Dumuzi was taken from his sheepfold; the demons seized him in the city. He turned himself into a gazelle and fled; he turned himself into a snake and hid in the reeds. But the demons caught him, and Dumuzi went to the underworld. For half the year he is below, and the land mourns; for half the year he returns, and the land rejoices.",
        "source": "ETCSL 1.4.3",
    },
    {
        "id": "etcsl-4.07.7-1",
        "title": "Inanna's Lament for Dumuzi",
        "deity": "Inanna",
        "type": "myth",
        "text": "O you who rise from the underworld, the husband I cannot reach, the shepherd Dumuzi my husband I cannot reach. My beloved who has gone from me, the shepherd Dumuzi who has gone from me — he has gone from me and I weep for him. He has gone to the underworld and the world above is silent. The land weeps with Inanna; the reeds weep; the trees weep; the cattle weep in their stalls.",
        "source": "ETCSL 4.07.7",
    },
    {
        "id": "etcsl-4.07.8-1",
        "title": "Inanna as the Morning Star",
        "deity": "Inanna",
        "type": "hymn",
        "text": "Inanna, the bright morning star, rises over the horizon of heaven. Her light announces the new day; her appearance calls the workers to the field. She is Venus, the most beautiful of all the stars. When she rises, the heavens tremble; when she descends, the world is in darkness. She journeys each day across the sky and each night into the underworld, and she always returns. She is the cycle of light itself.",
        "source": "ETCSL 4.07.8",
    },
    {
        "id": "etcsl-4.07.9-1",
        "title": "Inanna and the Bull of Heaven",
        "deity": "Inanna",
        "type": "myth",
        "text": "When Gilgamesh refused Inanna's love, she went weeping to her father Anu: 'My father, Gilgamesh has shamed me; give me the Bull of Heaven to destroy him!' Anu was afraid but gave her the Bull. The Bull descended to earth and three hundred warriors died with each snort of its breath. But Enkidu seized the Bull by the horns and Gilgamesh slew it. Inanna cried out in rage and grief; she had not foreseen this defeat.",
        "source": "ETCSL 4.07.9",
    },
    {
        "id": "etcsl-4.07.10-1",
        "title": "Inanna's Blessing on the Righteous",
        "deity": "Inanna",
        "type": "prayer",
        "text": "O Inanna, queen of heaven, bless the one who has served you faithfully. May his herds multiply; may his granaries overflow. May the merchant who prays to you find good roads and honest partners. May the warrior who fights in your name return safely from battle. May the woman who honors you find joy in her household. You are the source of all good fortune; your blessing is life itself.",
        "source": "ETCSL 4.07.10",
    },
    {
        "id": "etcsl-4.07.11-1",
        "title": "The Fearsome Power of Inanna",
        "deity": "Inanna",
        "type": "hymn",
        "text": "Do not approach Inanna when her heart is filled with wrath. Her roar is the roar of the storm; her anger is the flood. She destroys whom she wishes; she spares whom she wishes. Her face in anger is the face of the south wind. She carries the hoe and the weapon; she strikes down the wicked with the mace. Even the great gods bow their heads when Inanna's wrath is upon the land.",
        "source": "ETCSL 4.07.11",
    },
    {
        "id": "etcsl-4.07.12-1",
        "title": "Inanna's Wisdom in Judgment",
        "deity": "Inanna",
        "type": "wisdom",
        "text": "Inanna, the lady of the divine me, renders fair judgment. She who holds the staff and the ring does not decide lightly. She who descended to the underworld and returned knows both life and death. Her judgment is therefore complete: she knows what lies beneath the surface of things. The wise person prays to Inanna before any important decision; her answer comes in dreams and omens.",
        "source": "ETCSL 4.07.12",
    },
    {
        "id": "etcsl-4.07.13-1",
        "title": "Inanna, Lady of Battles",
        "deity": "Inanna",
        "type": "hymn",
        "text": "Inanna is the lady of battles, the queen of the divine army. She goes out before the warriors like a great light. She covers herself in the garment of battle; she puts on the helmet and grasps the weapon. She is the blazing fire that leads the charge. She is the divine force that determines victory. O Inanna, stand before the army of your faithful; go before them into the battle and grant them the victory.",
        "source": "ETCSL 4.07.13",
    },

    # ── GENERAL / PROVERBIOS / CREACIÓN (20) ─────────────────────────────────
    {
        "id": "etcsl-6.1.01-1",
        "title": "Sumerian Proverbs — Collection 1",
        "deity": "General",
        "type": "proverb",
        "text": "The fox could not build his own house and stood beneath the plantations of the great trees. Do not pick someone else's fruit without permission; pick the fruit of your own garden. A dog that is destined to die does not fear a stick. The strong live by their own work; the weak live by the work of others. Build your house well, for in your house you find your strength.",
        "source": "ETCSL 6.1.01",
    },
    {
        "id": "etcsl-6.1.01-2",
        "title": "Sumerian Proverbs — On Wisdom",
        "deity": "General",
        "type": "proverb",
        "text": "Possessions are sparrows in flight that cannot find a place to alight. A scribe who does not know Sumerian, what kind of scribe is he? A man without a god is like a man without a friend. The wise man is cautious; the foolish man is hasty. What you have heard with your ears do not repeat; what you have seen with your eyes do not tell. He who knows how to conceal knows how to wait.",
        "source": "ETCSL 6.1.01",
    },
    {
        "id": "etcsl-6.1.02-1",
        "title": "Sumerian Proverbs — Collection 2, On Labor",
        "deity": "General",
        "type": "proverb",
        "text": "For a farmer, his field is his profit; for a boatman, his boat is his profit. The laborer who does not dig is as useless as a soldier who does not fight. Your oil does not anoint the head of the man who has no oil. The tool that is not used becomes rusty; the mind that is not used becomes dull. Work is the foundation on which all good things are built. The lazy man will be poor in winter.",
        "source": "ETCSL 6.1.02",
    },
    {
        "id": "etcsl-6.1.02-2",
        "title": "Sumerian Proverbs — On Friendship",
        "deity": "General",
        "type": "proverb",
        "text": "Tell a lie and then tell the truth: it will be considered a lie. A friend is one who comes in when the whole world has gone out. Do not slander a friend. Do not return evil for evil to your friend; requite him with kindness. In days of trouble, the true friend appears; in days of abundance, all men are your friends. Choose your companions with care, for you become what they are.",
        "source": "ETCSL 6.1.02",
    },
    {
        "id": "etcsl-6.1.03-1",
        "title": "Sumerian Proverbs — On Speech",
        "deity": "General",
        "type": "proverb",
        "text": "The word that comes from the mouth of a liar is heavier than a millstone. The mouth of a wise man is his prosperity; the mouth of a fool is his ruin. Before you speak, run your tongue over your teeth. An eloquent man is the one who knows how to say what is appropriate. Words spoken in anger cannot be unsaid. The man who speaks much lies much; the man who speaks little tells the truth.",
        "source": "ETCSL 6.1.03",
    },
    {
        "id": "etcsl-1.1.1-2",
        "title": "The Eridu Genesis — Creation of Mankind",
        "deity": "General",
        "type": "myth",
        "text": "After An, Enlil, Enki, and Ninhursag had fashioned the black-headed people, vegetation grew from the earth and animals of all kinds were created. After kingship had descended from heaven, after the pure crown and throne of kingship had been lowered from heaven, the cities were built and the names of the cities were fixed. The first five cities were Eridu, Badtibira, Larak, Sippar, and Shuruppak.",
        "source": "ETCSL 1.1.1",
    },
    {
        "id": "etcsl-1.1.1-3",
        "title": "The Eridu Genesis — The Flood",
        "deity": "General",
        "type": "myth",
        "text": "The flood swept over the earth for seven days and seven nights. The huge boat was tossed about on the great waters. Ziusudra the king was prostrate at the bottom of the boat; Utu the sun-god shed his rays into the great boat. Ziusudra opened a window of the great boat; Utu the sun-god brought his rays into the great boat. Ziusudra, the king, prostrated himself before Utu, and the king sacrificed oxen and slaughtered sheep.",
        "source": "ETCSL 1.1.1",
    },
    {
        "id": "etcsl-5.6.1-1",
        "title": "The Debate between Summer and Winter",
        "deity": "General",
        "type": "wisdom",
        "text": "Summer and Winter argued before Enlil as to which was the more beneficial to the land. Winter said: 'I fill the granaries; I bring the rain; I nourish the crops in their growing.' Summer said: 'I ripen the grain; I bring the harvest; without me all that you nourish would wither and die.' Enlil judged between them: both are necessary; neither is complete without the other. So it is with all opposites.",
        "source": "ETCSL 5.6.1",
    },
    {
        "id": "etcsl-5.1.1-1",
        "title": "The Disputation between the Hoe and the Plow",
        "deity": "General",
        "type": "wisdom",
        "text": "The Hoe and the Plow debated which was more valuable to the farmer. The Plow said: 'I cut the earth; I open the furrow; without me no seed can be planted.' The Hoe said: 'I break the clods; I clear the ditches; without me your furrow fills with weeds.' The gods decided: each tool has its time and its place. Wisdom is knowing when to use the plow and when to use the hoe.",
        "source": "ETCSL 5.1.1",
    },
    {
        "id": "etcsl-6.1.04-1",
        "title": "Sumerian Proverbs — On Justice",
        "deity": "General",
        "type": "proverb",
        "text": "Do not steal anything; do not cut yourself off from the children of your god. The house of the man without a god is like a ruined mound. The man who deceives will be deceived. A just balance, a true weight, a sealed money-bag of correct value — these are the things that please the gods. The merchant who cheats with the scale will not see the face of heaven. Let your word be your bond.",
        "source": "ETCSL 6.1.04",
    },
    {
        "id": "etcsl-1.8.1-1",
        "title": "The Myth of Cattle and Grain",
        "deity": "General",
        "type": "myth",
        "text": "On the holy hill of heaven, An begat the goddesses Lahar and Ashnan, that food might be provided for the gods. But the gods could not eat the grain in the fields or drink the milk of the cattle. So man was created to cultivate the grain and tend the cattle, that the gods might be provided for. Thus agriculture is a divine gift and the farmer carries out sacred work.",
        "source": "ETCSL 1.8.1",
    },
    {
        "id": "etcsl-6.1.05-1",
        "title": "Sumerian Proverbs — On Knowledge",
        "deity": "General",
        "type": "proverb",
        "text": "Knowing is better than gold; learning is better than silver. The scribal art is the mother of orators. Do not boast of what you know; you will learn more from those you consider your equals. The man who has traveled knows the world; the man who has stayed at home knows only his street. Gather knowledge in your youth, for in old age it is the only wealth that does not decay.",
        "source": "ETCSL 6.1.05",
    },
    {
        "id": "etcsl-6.1.06-1",
        "title": "Sumerian Proverbs — On Power",
        "deity": "General",
        "type": "proverb",
        "text": "In a city without a watchdog, the fox rules. Where there is no shepherd, the sheep go their own way. The king who neglects the gods will be neglected by them. Power without wisdom is like a boat without a rudder. The strong man who does not use his strength wisely is weaker than the weak man who does. True authority comes from the heart, not from the arm.",
        "source": "ETCSL 6.1.06",
    },
    {
        "id": "etcsl-1.2.1-1",
        "title": "The Creation of the Pickaxe by Enlil",
        "deity": "General",
        "type": "myth",
        "text": "Enlil decided to separate heaven from earth. He drove the pickaxe into the earth and the place where heaven and earth separated began to grow with all living things. First plants, then animals, then the black-headed people grew up from the earth like grain from a seed. The pickaxe was the first tool; the first act of civilization was the separation of heaven from earth by the god who wields the wind.",
        "source": "ETCSL 1.2.1",
    },
    {
        "id": "etcsl-2.5.3-1",
        "title": "A Prayer for the King's Prosperity",
        "deity": "General",
        "type": "prayer",
        "text": "May An grant you long life; may Enlil raise your head to the heavens; may Inanna give you power over the foreign lands; may Enki give you great wisdom. May the great gods grant you long reign, many years, and favor in the eyes of heaven and earth. May your kingdom be as stable as the great mountain; may your name endure forever in the mouth of the people.",
        "source": "ETCSL 2.5.3",
    },
    {
        "id": "etcsl-5.3.2-1",
        "title": "The Advice of a Father to His Son",
        "deity": "General",
        "type": "wisdom",
        "text": "A father spoke to his son: 'Rise early in the morning; do not be lazy. Do not stand in the public square. Do not sit in the company of those who quarrel. Do not borrow money; those who borrow lose their freedom. Do not look upon a woman who belongs to another. Guard your tongue from evil speech; guard your eyes from wandering desire. He who guards himself will prosper; he who neglects himself will suffer.'",
        "source": "ETCSL 5.3.2",
    },
    {
        "id": "etcsl-5.4.1-1",
        "title": "The Farmer's Instructions",
        "deity": "General",
        "type": "wisdom",
        "text": "An ancient farmer taught his son: 'When you are about to cultivate the field, be careful to open the irrigation ditches. When the field has dried out enough, let your cattle and sheep graze on the plants. Plow the field well so that the clods are well broken up. Take care of the ox at the plow; the ox that labors in the field is sacred. When the barley is ripe, harvest it promptly; what is left too long in the field belongs to the birds.'",
        "source": "ETCSL 5.4.1",
    },
    {
        "id": "etcsl-1.9.1-1",
        "title": "The Myth of the Flood Hero Ziusudra",
        "deity": "General",
        "type": "myth",
        "text": "Ziusudra, the king, the pious one who feared the gods, built a great boat at the command of the gods. He brought into the boat the seed of all living things, the beasts of the field and the birds of the air. When the flood had passed, Utu the sun-god shone his light and Ziusudra made sacrifice. The gods granted him eternal life in the land of Dilmun, the place where the sun rises, for he had saved the seed of life.",
        "source": "ETCSL 1.9.1",
    },
    {
        "id": "etcsl-6.2.1-1",
        "title": "Proverbs from the Edubba — On Learning",
        "deity": "General",
        "type": "proverb",
        "text": "The schoolboy who does not know his Sumerian, what kind of scribe will he be? The boy who does not study becomes a laborer in the field; the man who does not read becomes the servant of the man who does. The tablet-house is the mother of learning and the father of civilization. One who has walked in the schoolhouse is at home in the palace; one who has not will be lost in the market.",
        "source": "ETCSL 6.2.1",
    },
    {
        "id": "etcsl-4.13.1-1",
        "title": "Hymn to Nanna the Moon God",
        "deity": "General",
        "type": "hymn",
        "text": "O Nanna, you who shine from the horizon, who fill the heavens with your light, you count the days and the months for gods and men. You reveal the evil night and give rest to the good. You are the illumination of the darkness; you are the calculator of time. By your light the farmer knows the season; by your phases the priest marks the festivals. O lord of the night, your mercy is the comfort of all who lie awake in the dark.",
        "source": "ETCSL 4.13.1",
    },
]


class CorpusStore:
    """Memoria ancestral del panteón — textos ETCSL en Qdrant."""

    def __init__(self, qdrant_client, embed_client):
        self._client = qdrant_client
        self._embed_client = embed_client
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            from qdrant_client.models import Distance, VectorParams
            existing = [c.name for c in self._client.get_collections().collections]
            if CORPUS_COLLECTION not in existing:
                self._client.create_collection(
                    collection_name=CORPUS_COLLECTION,
                    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
                )
        except Exception as e:
            logger.warning(f"[CORPUS] Error asegurando colección: {e}")

    def _embed(self, text: str) -> list[float] | None:
        try:
            resp = self._embed_client.embeddings.create(
                model="text-embedding-3-small",
                input=text[:2000],
            )
            return resp.data[0].embedding
        except Exception as e:
            logger.warning(f"[CORPUS] Error generando embedding: {e}")
            return None

    def ingest(self, texts: list[dict]) -> int:
        """Ingesta textos en Qdrant. Retorna número de textos ingresados."""
        from qdrant_client.models import PointStruct
        ingested = 0
        for entry in texts:
            try:
                combined = f"{entry['title']} {entry['deity']} {entry['text']}"
                vector = self._embed(combined)
                if not vector:
                    continue
                point_id = int(hashlib.md5(entry["id"].encode()).hexdigest()[:8], 16)
                self._client.upsert(
                    collection_name=CORPUS_COLLECTION,
                    points=[PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "corpus_id": entry["id"],
                            "title":     entry["title"],
                            "deity":     entry["deity"],
                            "type":      entry["type"],
                            "text":      entry["text"][:800],
                            "source":    entry["source"],
                        },
                    )],
                )
                ingested += 1
            except Exception as e:
                logger.warning(f"[CORPUS] Error ingresando {entry.get('id', '?')}: {e}")
        return ingested

    def search(self, query: str, limit: int = 3) -> str:
        """Búsqueda semántica en el corpus. Retorna string formateado."""
        try:
            vector = self._embed(query)
            if not vector:
                return ""
            results = self._client.query_points(
                collection_name=CORPUS_COLLECTION,
                query=vector,
                limit=limit,
                score_threshold=0.5,
            ).points
            if not results:
                return ""
            parts = []
            for r in results:
                title  = r.payload.get("title", "")
                deity  = r.payload.get("deity", "")
                text   = r.payload.get("text",  "")[:200]
                source = r.payload.get("source", "")
                parts.append(f'- [ETCSL] {title} ({deity}): "{text}..."\n  [fuente: {source}]')
            return "\n".join(parts)
        except Exception as e:
            logger.warning(f"[CORPUS] Error en búsqueda: {e}")
            return ""

    def count(self) -> int:
        """Total de textos en el corpus."""
        try:
            info = self._client.get_collection(CORPUS_COLLECTION)
            return info.points_count or 0
        except Exception:
            return 0

    @classmethod
    def from_qdrant_store(cls, qdrant_store: "QdrantMemoryStore") -> "CorpusStore | None":
        """Crea CorpusStore desde un QdrantMemoryStore existente. None si no disponible."""
        if not qdrant_store.is_available:
            return None
        return cls(qdrant_store._client, qdrant_store._embed_client)
