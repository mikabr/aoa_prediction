import nltk
from nltk.corpus.reader import CHILDESCorpusReader
#from nltk.stem.snowball import SnowballStemmer

import snowballstemmer
import re
import os
from collections import defaultdict
from unicode_csv import *

corpus_root = nltk.data.find('corpora/childes/data-xml/')

# Takes a language, returns a CHIDLESCorpusReader for that language
def get_corpus_reader(language):
    return CHILDESCorpusReader(corpus_root, r'%s.*/.*\.xml' % language[:3].title())

# Takes a language, returns a list of all of the CDI items for that language
def get_cdi_items(language):
    cdi_items = codecs.open('data/%s/%s_cdi_items.txt' % (language, language), "r", "utf-8").read().split("\n")
    return [item.lower() for item in cdi_items if len(item)]

# Takes a language and a Stemmer object, returns the stemmed special cases for that language
def get_special_cases(language, stemmer):
    special_cases = defaultdict(set)

    language_file = 'data/%s/%s_special_cases.csv' % (language, language)

    if not os.path.isfile(language_file):
        return special_cases

    with open(language_file, 'r') as langfile:
        special_case_list = UnicodeReader(langfile)

        for row in special_case_list:
            cdi_item, options = row[0], row[1:]
            if len(cdi_item) > 0:
                for option in options:
                    if len(option) > 0:
                        special_cases[option].add(cdi_item)
                        special_cases[stemmer(option)].add(cdi_item)
    return special_cases

# Takes a language, returns a Stemmer object for that language
def get_stemmer(language):
    stemmer_languages = ["danish", "dutch", "english", "finnish", "french", "german", "hungarian", "italian",
                         "norwegian", "portuguese", "romanian", "russian", "spanish", "swedish", "turkish"]
    if language.lower() in stemmer_languages:
        return lambda word: snowballstemmer.stemmer(language).stemWord(word)
    return lambda word: word
    #return lambda word: nltk.SnowballStemmer(language, ignore_stopwords = True).stem(word)

# Takes a CDI item, generates a list of alternate forms of that item
# Returns a dictionary from alternate forms to the original item
def get_pattern_options(item):
    split_item = item.split("/")
    options = []
    for splitted in split_item:
        patterns = [r"^(.+)[*]$", # mommy*
                    r"^(.+)\s[(].*$", # chicken (animal)
                    r"^(.+)\s\1$"] # woof woof
        for pattern in patterns:
            match = re.search(pattern, splitted)
            if match:
                options += match.groups()
        if ' ' in splitted:
            spaces = splitted.split(" ")
            options += [''.join(spaces), '_'.join(spaces), '+'.join(spaces)]
    options = set(options) | set(split_item)
    return options

def dict_union(a, b):
    return dict(a.items() + b.items() + [(k, a[k] | b[k]) for k in set(b) & set(a)])

# Takes a Stemmer object, a list of items, and a dictionary of special cases
# Returns a dictionary from all original forms, alternate forms, and special cases to CDI items
def get_lang_map(stemmer, cdi_items, special_cases):

    #lang_map = {item: {item} for item in cdi_items}
    #lang_map.update(special_cases)

    pattern_map = defaultdict(set)
    for item in cdi_items:
        options = get_pattern_options(item)
        for option in options:
            pattern_map[option].add(item)
    #lang_map.update(pattern_map)

    prestem_map = reduce(dict_union, [{item: {item} for item in cdi_items}, special_cases, pattern_map])

    #stem_map = {stemmer(item): {item} for item in cdi_items}
    stem_map = {stemmer(key): value for key, value in prestem_map.iteritems()}
    #lang_map.update(stem_map)

    lang_map = dict_union(prestem_map, stem_map)
    #lang_map = reduce(dict_union, [{item: {item} for item in cdi_items}, special_cases, pattern_map, stem_map])

    return lang_map

# Takes a CorpusReader object, a stemmer, and a dictionary from alternate forms to items
# Returns a FreqDist of all items in the lang_map for the corpus in the CorpusReader
def get_lang_stats(corpus_reader, stemmer, lang_map):

    freqs = nltk.FreqDist()
    lengths = defaultdict(list)
    for corpus_file in corpus_reader.fileids():#[0:20]:
        corpus_participants = corpus_reader.participants(corpus_file)[0]
        #age = allEnglish.age(file, month=True)
        not_child = [value['id'] for key, value in corpus_participants.iteritems() if key != 'CHI']

        corpus_sents = corpus_reader.sents(corpus_file, speaker = not_child, replace = True)
        for sent in corpus_sents:
            for word in sent:
                stem = stemmer(word.lower())
                lengths[stem].append(len(sent))
                freqs[stem] += 1


#        corpus_words = corpus_reader.words(corpus_file, speaker=not_child, replace = True)
#        corpus_stems = [stemmer(word.lower()) for word in corpus_words]
#        freqs.update(nltk.FreqDist(corpus_stems))

    cdi_lengths = defaultdict(list)
    for word, word_lengths in lengths.iteritems():
        if word in lang_map:
            items = lang_map[word]
            for item in items:
                cdi_lengths[item] += word_lengths
    cdi_mlus = {item: float(sum(item_lengths)) / len(item_lengths) for item, item_lengths in cdi_lengths.iteritems()}

    sgt = nltk.SimpleGoodTuringProbDist(freqs)
    freq_sum = sum(freqs.values())
    # cdi_freqs = defaultdict(float)
    cdi_freqs = defaultdict(lambda: defaultdict(float))

    for key, value in freqs.iteritems():
        if key in lang_map:
            items = lang_map[key]
            for item in items:
                # cdi_freqs[item] += float(value)/len(items)
                cdi_freqs[item]['count'] += float(value)/len(items)
                cdi_freqs[item]['probability'] += sgt.prob(item)
    unseen = '!!!!!'
    cdi_freqs[unseen]['probability'] += sgt.prob(unseen)
    cdi_freqs[unseen]['frequency'] += 0
    norm_cdi_freqs = {item : {'probability': values['probability'], 'frequency': values['count'] / freq_sum} for item, values in cdi_freqs.iteritems()}

    return norm_cdi_freqs, cdi_mlus

def get_stats(language):
    lang_stemmer = get_stemmer(language)
    cdi_items = get_cdi_items(language)
    cdi_freqs, cdi_mlus = get_lang_stats(get_corpus_reader(language), lang_stemmer,
                                    get_lang_map(lang_stemmer, cdi_items,
                                                 get_special_cases(language, lang_stemmer)))
    print language, float(len(cdi_freqs)) / len(cdi_items)
    return cdi_freqs, cdi_mlus

def write_freqs(language, freqs):
    with open("freqs/freqs_%s.csv" % language.lower(), "w") as freq_file:
        freq_writer = UnicodeWriter(freq_file)
        freq_writer.writerow(["item", "probability", "frequency"])
        for item, values in freqs.iteritems():
            freq_writer.writerow([item, str(values['probability']), str(values['frequency'])])

def write_mlus(language, mlus):
    with open("mlus/mlus_%s.csv" % language.lower(), "w") as mlu_file:
        mlu_writer = UnicodeWriter(mlu_file)
        mlu_writer.writerow(["item", "mlu"])
        for item, value in mlus.iteritems():
            mlu_writer.writerow([item, str(value)])

# def get_lang_counts(language):
#     corpus_reader = get_corpus_reader(language)
#     stemmer = get_stemmer(language)
#     counts = nltk.FreqDist()
#     for corpus_file in corpus_reader.fileids():
#         corpus_participants = corpus_reader.participants(corpus_file)[0]
#         not_child = [value['id'] for key, value in corpus_participants.iteritems() if key != 'CHI']
#         corpus_words = corpus_reader.words(corpus_file, speaker=not_child)
#         corpus_stems = [stemmer(word.lower()) for word in corpus_words]
#         counts.update(nltk.FreqDist(corpus_stems))
#     return counts
#
# def write_lang_counts(language, lang_counts):
#     with open("counts/counts_%s.csv" % language.lower(), "w") as count_file:
#         count_writer = UnicodeWriter(count_file)
#         count_writer.writerow(["item", "count"])
#         for item, count in lang_counts.iteritems():
#             count_writer.writerow([item, str(count)])

def get_num_words(language):
    num_words = 0
    corpus_reader = get_corpus_reader(language)
    for corpus_file in corpus_reader.fileids():
        corpus_participants = corpus_reader.participants(corpus_file)[0]
        not_child = [value['id'] for key, value in corpus_participants.iteritems() if key != 'CHI']
        corpus_words = corpus_reader.words(corpus_file, speaker = not_child, replace = True)
        num_words += len(corpus_words)
    return num_words

languages = ["italian", "norwegian", "russian", "spanish", "swedish", "turkish", "english"]
             #"danish", "german", "cantonese" "hebrew" "mandarin" "croatian"
# for language in languages:
#     lang_freqs, lang_mlus = get_stats(language)
#     write_freqs(language, lang_freqs)
#     write_mlus(language, lang_mlus)

with open("num_words.csv", "w") as num_words_file:
    num_words_writer = UnicodeWriter(num_words_file)
    num_words_writer.writerow(["language", "num_words"])
    for language in languages:
        num_words = get_num_words(language)
        print language, num_words
        num_words_writer.writerow([language.capitalize(), str(num_words)])

#eng = get_freqs("English")

#get_freqs("hebrew")
#get_freqs("english")
# language = "hebrew"
# stemmer = get_stemmer(language)
# corpus_reader = get_corpus_reader(language)
# freqs = nltk.FreqDist()
# for corpus_file in corpus_reader.fileids():#[0:20]:
#     corpus_participants = corpus_reader.participants(corpus_file)[0]
#     not_child = [value['id'] for key, value in corpus_participants.iteritems() if key != 'CHI']
#     corpus_words = corpus_reader.words(corpus_file, speaker=not_child)
#     corpus_stems = [stemmer(word.lower()) for word in corpus_words]
#     freqs.update(nltk.FreqDist(corpus_words))
# words = sorted(freqs.keys())
# with codecs.open("hebrew_words.txt", 'w', 'utf-8') as heb:
#     for w in words:
#         heb.write(w)
#         heb.write('\n')