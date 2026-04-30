pub fn normalize_whitespace(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut needs_space = false;

    for part in text.split_whitespace() {
        if needs_space {
            output.push(' ');
        }
        output.push_str(part);
        needs_space = true;
    }

    output
}

pub fn clean_text(text: &str) -> String {
    let without_tags = strip_html_noise(text);

    normalize_whitespace(&without_tags)
}

fn strip_html_noise(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut index = 0;

    while index < text.len() {
        let remaining = &text[index..];

        if remaining.starts_with('<') {
            let Some(tag_end_offset) = remaining.find('>') else {
                output.push_str(remaining);
                break;
            };

            let tag_end = index + tag_end_offset;
            let tag = &text[index + 1..tag_end];

            if is_opening_tag(tag, "script") {
                index = skip_block(text, tag_end + 1, "script");
                output.push(' ');
                continue;
            }

            if is_opening_tag(tag, "style") {
                index = skip_block(text, tag_end + 1, "style");
                output.push(' ');
                continue;
            }

            output.push(' ');
            index = tag_end + 1;
            continue;
        }

        let character = remaining.chars().next().expect("remaining text is not empty");
        output.push(character);
        index += character.len_utf8();
    }

    output
}

fn skip_block(text: &str, start: usize, tag: &str) -> usize {
    let close_prefix = format!("</{}", tag);

    let Some(close_start) = find_ascii_case_insensitive(text, start, &close_prefix) else {
        return text.len();
    };

    let Some(close_end_offset) = text[close_start..].find('>') else {
        return text.len();
    };

    close_start + close_end_offset + 1
}

fn is_opening_tag(tag: &str, expected: &str) -> bool {
    let trimmed = tag.trim_start();

    if trimmed.starts_with('/') || trimmed.starts_with('!') || trimmed.starts_with('?') {
        return false;
    }

    let name = trimmed
        .split(|character: char| character.is_whitespace() || character == '/' || character == '>')
        .next()
        .unwrap_or("");

    name.eq_ignore_ascii_case(expected)
}

fn find_ascii_case_insensitive(haystack: &str, start: usize, needle: &str) -> Option<usize> {
    let haystack_bytes = haystack.as_bytes();
    let needle_bytes = needle.as_bytes();

    if needle_bytes.is_empty() || start >= haystack_bytes.len() {
        return None;
    }

    haystack_bytes[start..]
        .windows(needle_bytes.len())
        .position(|window| {
            window
                .iter()
                .zip(needle_bytes.iter())
                .all(|(left, right)| left.eq_ignore_ascii_case(right))
        })
        .map(|relative_position| start + relative_position)
}
