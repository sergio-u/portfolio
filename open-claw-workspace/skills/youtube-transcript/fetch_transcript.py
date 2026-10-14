#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["youtube-transcript-api"]
# ///
"""Fetch the transcript/captions of a YouTube video."""

import argparse
import json
import re
import sys

from youtube_transcript_api import YouTubeTranscriptApi


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch transcript/captions from a YouTube video."
    )
    parser.add_argument(
        "video",
        help="YouTube video URL or video ID",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=["en"],
        help="Language codes in descending priority (default: en)",
    )
    parser.add_argument(
        "--translate",
        metavar="LANG",
        default=None,
        help="Translate transcript to this language code (e.g. 'en', 'es')",
    )
    parser.add_argument(
        "--list-transcripts",
        action="store_true",
        default=False,
        help="List available transcripts instead of fetching one",
    )
    parser.add_argument(
        "--output-format",
        choices=["text", "json", "timestamped"],
        default="text",
        help="Output format (default: text). "
             "'text' = plain transcript, "
             "'json' = raw snippet data, "
             "'timestamped' = text with [MM:SS] timestamps",
    )
    parser.add_argument(
        "--preserve-formatting",
        action="store_true",
        default=False,
        help="Preserve HTML formatting (bold, italic) in transcript text",
    )
    return parser.parse_args()


def extract_video_id(video: str) -> str:
    """Extract the video ID from a URL or return as-is if already an ID."""
    # Full URL patterns
    patterns = [
        r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, video)
        if match:
            return match.group(1)

    # If it looks like a bare video ID (11 chars, valid characters)
    if re.match(r"^[a-zA-Z0-9_-]{11}$", video):
        return video

    # Last resort: return as-is and let the API error out
    return video


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def list_transcripts(video_id: str) -> None:
    """List available transcripts for a video."""
    ytt_api = YouTubeTranscriptApi()
    transcript_list = ytt_api.list(video_id)

    transcripts = []
    for transcript in transcript_list:
        entry = {
            "language": transcript.language,
            "language_code": transcript.language_code,
            "is_generated": transcript.is_generated,
            "is_translatable": len(transcript.translation_languages) > 0,
        }
        transcripts.append(entry)

    print(json.dumps(transcripts, indent=2))


def fetch_transcript(
    video_id: str,
    languages: list[str],
    translate_to: str | None,
    output_format: str,
    preserve_formatting: bool,
) -> None:
    """Fetch and output a transcript."""
    ytt_api = YouTubeTranscriptApi()

    if translate_to:
        # Need to go through list -> find -> translate -> fetch
        transcript_list = ytt_api.list(video_id)
        transcript = transcript_list.find_transcript(languages)
        fetched = transcript.translate(translate_to).fetch(
            preserve_formatting=preserve_formatting
        )
    else:
        fetched = ytt_api.fetch(
            video_id,
            languages=languages,
            preserve_formatting=preserve_formatting,
        )

    # Build metadata
    metadata = {
        "video_id": fetched.video_id,
        "language": fetched.language,
        "language_code": fetched.language_code,
        "is_generated": fetched.is_generated,
    }

    if output_format == "json":
        output = {
            **metadata,
            "snippets": fetched.to_raw_data(),
        }
        print(json.dumps(output, indent=2))
    elif output_format == "timestamped":
        # Print metadata as a header
        kind = "auto-generated" if fetched.is_generated else "manual"
        print(
            f"# Transcript: {fetched.language} ({fetched.language_code}, {kind})"
        )
        print()
        for snippet in fetched:
            ts = format_timestamp(snippet.start)
            print(f"[{ts}] {snippet.text}")
    else:
        # Plain text -- just concatenate all snippet texts
        kind = "auto-generated" if fetched.is_generated else "manual"
        print(
            f"# Transcript: {fetched.language} ({fetched.language_code}, {kind})"
        )
        print()
        text = " ".join(snippet.text for snippet in fetched)
        print(text)


def main() -> None:
    args = parse_args()
    video_id = extract_video_id(args.video)

    try:
        if args.list_transcripts:
            list_transcripts(video_id)
        else:
            fetch_transcript(
                video_id=video_id,
                languages=args.languages,
                translate_to=args.translate,
                output_format=args.output_format,
                preserve_formatting=args.preserve_formatting,
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
