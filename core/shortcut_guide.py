"""The guide to the keyboard: the keys that never change, then every menu with its commands'
shortcuts as they are now. Shown in the app as text, and saved as a text file or a web page.

The guide is (intro, sections): `intro` is the fixed part, paragraphs parted by blank lines,
where a paragraph of several lines is a heading followed by one item per line; each section is
(title, [(shortcut, command), ...]).
"""
import html

PAGE = """<!doctype html>
<html lang="{lang}" dir="{direction}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: "Segoe UI", Tahoma, sans-serif; max-width: 52em; margin: 2em auto; padding: 0 1em; line-height: 1.6; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5em; }}
th, td {{ border: 1px solid #999; padding: 0.3em 0.6em; text-align: start; }}
th {{ background: #eee; }}
kbd {{ font-family: Consolas, monospace; white-space: nowrap; }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>
"""


def to_text(intro, sections, line_format):
    """The guide as plain text, the way the app shows it."""
    parts = [intro]
    for title, rows in sections:
        parts.append("\n".join([title] + [line_format.format(shortcut=shortcut, command=command) for shortcut, command in rows]))
    return "\n\n".join(parts)


def to_html(title, intro, sections, lang, direction, shortcut_header, command_header):
    """The guide as a web page: a heading for each part, so a screen reader can go from one to the next,
    and each menu as a table of its shortcuts."""
    escape = html.escape
    body = []
    for paragraph in intro.split("\n\n"):
        lines = [line for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue
        if len(lines) == 1:
            body.append("<p>%s</p>" % escape(lines[0]))
        else:
            body.append("<h2>%s</h2>" % escape(lines[0]))
            body.append("<ul>\n%s\n</ul>" % "\n".join("<li>%s</li>" % escape(line) for line in lines[1:]))
    for section_title, rows in sections:
        body.append("<h2>%s</h2>" % escape(section_title))
        table = ["<table>", "<tr><th>%s</th><th>%s</th></tr>" % (escape(shortcut_header), escape(command_header))]
        table.extend(
            "<tr><td><kbd>%s</kbd></td><td>%s</td></tr>" % (escape(shortcut), escape(command)) for shortcut, command in rows
        )
        table.append("</table>")
        body.append("\n".join(table))
    return PAGE.format(lang=escape(lang), direction=escape(direction), title=escape(title), body="\n".join(body))
