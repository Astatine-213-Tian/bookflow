# Normalization Guide

This guide tells people what normalization does to the text of a book, and why.
It uses ASD-STE100 Simplified Technical English.

The rules in [normalization.md](normalization.md) are the only source of truth.
The code and the tests read that file. This guide gives the same rules in short
English with examples. If this guide and `normalization.md` do not agree, use
`normalization.md`.

## 1. What normalization is

Normalization makes the visible text of a book consistent. It changes characters,
spaces, punctuation and title formats. It does not change the meaning of the text.

Normalization operates on the shared book JSON. All inputs go into this JSON
first: crawled websites, EPUB files, TXT files, image transcriptions and
translations. Then normalization operates one time. Then the writers make the
EPUB, the TXT or the Notion page. The writers do not clean the text again.

Normalization obeys these limits:

- It does not guess a character that it cannot read.
- It does not rewrite a sentence.
- It does not remove a paragraph only because the format of the paragraph is
  unusual.
- It does not change a link target, an anchor, a footnote identity or a style.
- It does not search the web. It does not add metadata.
- It does not decide where a volume or a chapter starts. The input review gives
  that structure.

When a rule is not certain, normalization does not change the text. It puts the
item in the review report. A person or an agent then makes the decision.

## 2. Characters

### 2.1 Full-width letters and digits

Normalization changes full-width Latin letters and digits to half-width.

| Before | After |
| --- | --- |
| `ＭＳＮ，ＱＱ` | `MSN，QQ` |
| `１００分` | `100 分` |

Other full-width characters do not change. Chinese punctuation, `①`, `Ⅰ` and
`㎏` stay as they are.

### 2.2 English names

Normalization corrects the capital letters of known English names. The list of
names is in `src/content/english_terms.py`.

| Before | After |
| --- | --- |
| `iphone`, `IPHONE`, `iPhOnE` | `iPhone` |
| `github` | `GitHub` |

The rule changes only a complete English word. It does not correct spelling, so
`IPONE` does not change. These items do not change:

- Web addresses, email addresses, file names, account names and code.
- Names that are also usual words, for example `apple`, `python` and `word`.
- `MAC` in `MAC 地址`, because there it is not the name of a computer.

## 3. Spaces

Normalization puts one half-width space between a Chinese character and a Latin
letter, a Greek letter or a digit.

| Before | After |
| --- | --- |
| `S级` | `S 级` |
| `仙女座β星系` | `仙女座 β 星系` |
| `2012年` | `2012 年` |

Other space rules:

- A full-width space between two Latin words becomes one usual space:
  `NICE　DOGS` becomes `NICE DOGS`.
- Normalization removes the indent at the start of a paragraph.
- Normalization keeps line breaks in a paragraph.
- Normalization removes a space between Chinese characters only when the space is
  a known error. If the space can have a purpose, the space stays and goes into
  the review report.

## 4. Punctuation

In Chinese text, normalization changes ASCII punctuation to Chinese punctuation.
This applies to the comma, the full stop, the question mark, the exclamation mark,
the colon, the semicolon, and parentheses that contain Chinese text.

Normalization keeps ASCII punctuation in these items:

- Decimal numbers and thousands separators.
- Web addresses, file extensions and times.
- Emoticons and correct English sentences.
- Coordinates and similar codes. Here the comma stays, and one space comes after
  it: `X337,Y160` becomes `X337, Y160`.

Other punctuation rules:

- Chinese punctuation touches the text next to it. Normalization removes extra
  spaces near it.
- An ASCII ellipsis in Chinese text becomes `……`. A row of hyphens becomes a dash.
- Normalization removes a repeated Chinese comma. It also corrects clear errors at
  the end of a sentence, for example `，。`.
- `○` becomes `〇` only in a Chinese number.

## 5. Quotation marks

Chinese quotations use curved quotation marks that point in the correct
direction. Normalization corrects a quotation mark only when the context is clear.

| Before | After |
| --- | --- |
| `“哦。“` | `“哦。”` |

Normalization examines each paragraph with the paragraphs before and after it.
It does not count the quotation marks in the full chapter. Nested quotations,
quotations across many paragraphs, and English apostrophes (`I’ll`) do not change.

A paragraph can be a quotation block. Normalization does not decide this from
the font, the indent or the quotation marks. A separate review finds the
candidates. Only a high-confidence decision changes the block type.

## 6. Suspect text

Some text can be an error, but normalization cannot be sure. Normalization does
not replace this text. It puts the text in the review report. Examples:

- Unreadable characters, private-use characters and unusual control characters.
- Text that looks like an advertisement.
- A word that looks broken.

Normalization removes an advertisement only when it matches a known
advertisement exactly. A web address or an account name alone is not sufficient
to remove text.

Emoji, joiners and emoticons such as `/(ㄒoㄒ)/~~` stay.

## 7. Volume titles

These rules apply only to a title that the input review confirms as a volume.
They do not change the volume order, the chapters in the volume or the stable IDs.

- A volume number becomes a usual Chinese number. Formal numbers such as `壹`,
  `贰` and `叁` are not used.
- A volume title has the form `卷` + number + `·` + subtitle.
- All spaces in a volume title become one `·`. This rule also applies to a volume
  without a number.

| Before | After |
| --- | --- |
| `卷一 初识` | `卷一·初识` |
| `第一卷：初识` | `卷一·初识` |
| `卷１·初识` | `卷一·初识` |
| `第零卷` | `卷零` |
| `续卷 新的开始` | `续卷·新的开始` |
| `中卷` | `中卷` |

Only a clear `卷N` or `第N卷` label gets a number change. `续卷`, `中卷`, `上卷` and
`终卷` do not get a number. A year, for example `2015`, is not a volume number.

## 8. Chapter titles and extra stories

### 8.1 Chapter titles

A main chapter number uses half-width Arabic digits. One space comes between the
number and the title.

| Before | After |
| --- | --- |
| `第十二章 标题` | `第12章 标题` |
| `第１回` | `第1回` |
| `第〇〇一章` | `第1章` |

Normalization changes only a clear `第N章`, `第N回` or `第N节` at the start of the
title. It does not change the order of chapters. If a number is not in the
sequence, normalization does not add it. A number range, for example
`第94-95章`, stays. A year or a part number
in the title does not change.

In a title, a full stop that separates two parts becomes `·`. An English comma
becomes `，`.

### 8.2 Extra stories (番外)

- An independent extra story does not keep the `第N章` prefix of a main chapter.
- An extra-story number uses a Chinese number: `番外 1 飞天猫` becomes
  `番外一·飞天猫`.
- `番外：蜜月` becomes `番外·蜜月`.
- A volume that the author calls `番外卷` is part of the main text. Its chapters
  keep their main chapter numbers.

## 9. Structure in a chapter

### 9.1 Subheadings

A confirmed subheading in a chapter is a level-3 heading. A numbered subheading
is centered, and its number becomes a usual Chinese number.

| Before | After |
| --- | --- |
| `（1）` | `（一）` |
| `2、标题` | `二、标题` |

A paragraph that contains only a number becomes a subheading only when all of
these conditions are true:

- The numbers start at one.
- The numbers are continuous.
- There are two or more numbers.
- Each number has text after it.

### 9.2 Lists

A list item stays a usual paragraph. Its number has the form `1. `.
`１，第一项。` becomes `1. 第一项。`. Normalization finds a list only when the
numbers start at one, they are continuous, and there are two or more items.

### 9.3 Empty paragraphs and joined paragraphs

- Normalization removes empty paragraphs at the start of a chapter. It also
  removes empty paragraphs before and after a numbered subheading.
- Other empty paragraphs that separate scenes stay.
- Normalization joins two paragraphs only for a clear break error. An example is
  a quotation mark that closes a quotation and is alone on a line.
- Normalization does not join paragraphs across an empty paragraph, an author's
  note, a scene marker or a bilingual pair.

### 9.4 Author's notes

`作者有话说：` and `作者有话要说：` become a separate paragraph. The author's note
at the end of a chapter stays.

Normalization adds a divider before the label when all of these are true:

- A body paragraph comes before the label. Empty paragraphs between them are
  permitted.
- The note has text, on the label line or in the next paragraph.
- No divider is already there.

Notion and EPUB then show the text from the label to the end of the chapter as an
author's note. Normalization does not add a divider before a note at the start
of a chapter, a bilingual paragraph, or a paragraph with an anchor or footnote.
In an EPUB archive, the label paragraph and the body paragraph must be adjacent
`<p>` elements. Its text gets the same character, space,
punctuation and name rules as the main text.

### 9.5 Scene markers, dividers and end markers

| Item | Result |
| --- | --- |
| `***` on its own line | It is centered. |
| A line of three or more dashes only, for example `------------` | It becomes a divider: a Notion divider, or `<hr />` in an EPUB. |
| An end marker on its own line, for example `全文完` or `The End` | It becomes `——全文完——` and is centered. |
| A title and an end word, for example `第三部完` | It becomes `——第三部·完——`. |

A dash in a sentence does not change. The words `完`, `终` and `end` in a
sentence do not change.

## 10. Links, footnotes and bilingual text

- A link keeps its visible text, its style and its target.
- A footnote reference, for example `[1]`, stays paired with its note at the end
  of the chapter.
- In a bilingual book, the original text does not change. The translation gets
  the usual rules. Normalization does not join translation paragraphs across
  two pairs.

## 11. How to change a rule

Normalization must give the same result when it operates two times. Each rule
change must keep this property.

To change a rule, do these steps:

1. Change the rule in `docs/normalization.md`.
2. Change the code in `src/content/`.
3. Add or change the related example at the end of `docs/normalization.md`.
4. Put the new SHA-256 value of `docs/normalization.md` in `RULES_SHA256` in
   `src/content/normalize.py`.
5. Run the tests:
   `uv run python -m unittest discover -s tests -p 'test_*.py'`.
6. Update this guide.

The tests run the examples in `docs/normalization.md`. Preparation runs record
the rule file. After a rule change, an old run does not resume. Use a new run
directory.
