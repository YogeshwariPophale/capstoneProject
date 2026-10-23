#!/usr/bin/env python3
"""Fill the supplied project report template with the current project update."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "[Template] Project Report.docx"
OUTPUT = ROOT / "Project_Progress_Report.docx"
FIGURES = ROOT / "reports" / "eda" / "report_figures"


def replace_paragraph_text(paragraph: Paragraph, text: str, *, italic: bool = False,
                           size_pt: float = 14, bold: bool = False) -> None:
    for run in list(paragraph.runs):
        paragraph._p.remove(run._r)
    run = paragraph.add_run(text)
    run.font.size = Pt(size_pt)
    run.italic = italic
    run.bold = bold


def insert_paragraph_after(anchor: Paragraph, text: str | None = None,
                           *, size_pt: float = 14, italic: bool = False,
                           bold_prefix: str | None = None) -> Paragraph:
    element = OxmlElement("w:p")
    anchor._p.addnext(element)
    p = Paragraph(element, anchor._parent)
    p.style = anchor.part.document.styles["Normal"]
    p.paragraph_format.space_after = Pt(7)
    p.paragraph_format.line_spacing = 1.05
    if text:
        if bold_prefix and text.startswith(bold_prefix):
            r = p.add_run(bold_prefix)
            r.bold = True
            r.font.size = Pt(size_pt)
            r2 = p.add_run(text[len(bold_prefix):])
            r2.font.size = Pt(size_pt)
            r2.italic = italic
        else:
            r = p.add_run(text)
            r.font.size = Pt(size_pt)
            r.italic = italic
    return p


def insert_figure_after(anchor: Paragraph, filename: str, caption: str) -> Paragraph:
    element = OxmlElement("w:p")
    anchor._p.addnext(element)
    p = Paragraph(element, anchor._parent)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run()
    inline = run.add_picture(str(FIGURES / filename), width=Inches(6.35))
    inline._inline.docPr.set("descr", caption)
    cap = insert_paragraph_after(p, caption, size_pt=10, italic=True)
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(8)
    return cap


def save_with_template_parts(doc: Document) -> None:
    """Keep every untouched package part byte-identical to the retained template."""
    generated = OUTPUT.with_name(OUTPUT.stem + "_generated.docx")
    merged = OUTPUT.with_name(OUTPUT.stem + "_merged.docx")
    doc.save(generated)
    replaced = {"[Content_Types].xml", "word/document.xml", "word/_rels/document.xml.rels"}
    with ZipFile(TEMPLATE, "r") as original, ZipFile(generated, "r") as edited, ZipFile(merged, "w") as final:
        final.comment = original.comment
        original_names = set(original.namelist())
        for info in original.infolist():
            content = edited.read(info.filename) if info.filename in replaced else original.read(info.filename)
            final.writestr(info, content)
        for info in edited.infolist():
            if info.filename not in original_names:
                final.writestr(info, edited.read(info.filename))
    merged.replace(OUTPUT)
    generated.unlink()


def main() -> None:
    doc = Document(TEMPLATE)
    # The template's section headings and source paragraph objects are retained;
    # the six instructional prompt paragraphs become the report text slots.
    ps = doc.paragraphs
    title, metadata = ps[0], ps[1]
    intro, prior, dataset, milestones, results, conclusion = (ps[i] for i in (4, 7, 10, 13, 16, 19))

    replace_paragraph_text(title, "Interstate 5 Traffic Congestion Analysis and Short Term Prediction Progress Report",
                           size_pt=20)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    replace_paragraph_text(metadata, "Name: Yogeshwari Pophale                         NetID: __________",
                           size_pt=14)
    date_line = ps[2]
    replace_paragraph_text(date_line, "Reporting date: October 23, 2026", size_pt=12)

    replace_paragraph_text(intro,
        "This project examines Caltrans PeMS Station 5-Minute observations to describe traffic patterns on I-5 and prepare for short-term congestion forecasting. The current analysis covers District 12, both northbound and southbound directions, from January 1 through September 30, 2026. This is a progress update on the data preparation and exploratory analysis phase; no congestion label or forecasting model has been finalized.")
    cursor = insert_paragraph_after(intro,
        "The work so far establishes a reproducible I-5 dataset and a first set of time-of-day, weekday, data-quality, and timestamp-alignment summaries. These results identify promising patterns for follow-up, while also showing that missing dates, incomplete measurements, and the choice of station types must be resolved before the results can support a final model.")

    replace_paragraph_text(prior,
        "Lopez-Garcia, Onieva, Osaba, Masegosa, and Perallos (2016) studied a 9-km Sacramento I-5 corridor using September 2013 PeMS observations collected every five minutes. They classified traffic into free, slight, moderate, and severe states and forecast at 5-, 15-, and 30-minute horizons using a hierarchical fuzzy-rule system optimized with a Genetic Algorithm and Cross-Entropy method. The paper provides methodological context for short-horizon forecasting, but its corridor, dates, detector set, and classification rules are not directly transferable to this dataset.")
    cursor = insert_paragraph_after(prior,
        "The current project is adapting the short-horizon question to a newer District 12 dataset. Timestamp checks include 5-, 10-, and 15-minute histories and a 15-minute future target. The paper's printed speed and density intervals have overlapping boundaries and require unit and lane-convention review before any labels can be applied. No paper-derived congestion labels have been assigned.")
    cursor = insert_paragraph_after(cursor,
        "Reference: Lopez-Garcia, P., Onieva, E., Osaba, E., Masegosa, A. D., & Perallos, A. (2016). A hybrid method for short-term traffic congestion forecasting using genetic algorithms and cross entropy. IEEE Transactions on Intelligent Transportation Systems, 17(2), 557-567. https://doi.org/10.1109/TITS.2015.2491365.",
        size_pt=12)

    replace_paragraph_text(dataset,
        "The source is the Caltrans PeMS Station 5-Minute district product. The supplied District 12 files contain 175,057,116 district-wide records; filtering to District 12, freeway 5, and directions N and S retained 48,382,620 I-5 records from 715 station IDs. The retained data include 24,495,816 northbound and 23,886,804 southbound records. Each source record has 52 fields: timestamp, station and roadway identifiers, lane/station type, station-level measurement fields, and measurements for ten lane groups.")
    cursor = insert_paragraph_after(dataset,
        "All lane and station types are retained at this exploratory stage. The raw daily text files remain unchanged; the derived data are stored as nine monthly gzip-compressed CSV files with descriptive column names. The local collection contains files for 235 of the 273 calendar dates in the analysis window, including a multi-day gap in September. These are gaps in the supplied local files, not evidence that PeMS lacks the dates. The manifest records the missing dates and monthly row counts.")
    cursor = insert_paragraph_after(cursor,
        "The transformation found zero malformed-width rows and validated gzip integrity and monthly row totals. Monthly EDA found zero duplicate timestamp/station/direction/lane-type keys and parseable timestamps for all retained rows. These checks validate structure and selected consistency conditions; they do not establish that every measurement is analytically clean.")

    replace_paragraph_text(milestones,
        "Completed: preserved the raw source files, filtered the district data to I-5 in both directions, assigned consistent names to all 52 fields, and created monthly compressed analysis files with a manifest. Completed: ran monthly EDA for data quality, temporal patterns, traffic relationships, station summaries, sampling gaps, and timestamp alignment, plus cross-month comparisons for lane type, speed thresholds, and episode durations.")
    cursor = insert_paragraph_after(milestones,
        "In progress: validate station IDs, locations, postmiles, and station types against a PeMS station inventory; select the study segment and decide whether mainline, HOV, or ramp records belong in the primary analysis; and define how incomplete observations and missing dates will be handled.")
    cursor = insert_paragraph_after(cursor,
        "Next: finalize a quality rule and a congestion-label definition after confirming measurement units and lane conventions. Then build a chronological evaluation set and compare suitable persistence and machine-learning baselines for a 15-minute target. The present work has not trained or scored any forecasting model.")

    replace_paragraph_text(results,
        "The EDA shows a recurring hourly traffic cycle. Across the monthly summaries, flow rises during the morning, stays elevated through much of the day, and eases in the evening; speed generally declines as occupancy increases, particularly during busier hours. Monday-by-hour curves also vary by direction and month. The attached profile plots summarize available records only and combine lane and station types, so they are descriptive rather than corridor-specific or causal findings.")
    cursor = insert_paragraph_after(results,
        "Across monthly record-level relationship summaries, speed and occupancy have negative correlations ranging from about -0.60 to -0.69. Flow and speed correlations are much weaker, about -0.10 to -0.15. These pooled associations support examining occupancy alongside speed, but correlations across mixed station and lane types should not be interpreted as causal effects.")
    cursor = insert_paragraph_after(cursor,
        "Measurement completeness is a material limitation. Mean percent observed is about 65.1% to 79.3% from January through August, then falls to 15.7% in September; 85.6% of September records are below 90% observed. The multi-month temporal figures therefore use a provisional filter of at least 90% observed and retain all lane/station types. That filter is a sensitivity choice for these plots, not an approved modeling policy. September's curves in particular require cautious interpretation.")
    cursor = insert_paragraph_after(cursor,
        "Timestamp alignment is high in the retained records: exact 15-minute history and future timestamp matches range from about 99.83% to 99.96% by month. This measures usable timestamp keys, not forecast accuracy. Exploratory counts below 30, 40, and 50 mph and episode-duration scans are also available, but the project has not adopted these cutoffs as congestion labels.")
    cursor = insert_figure_after(cursor, "05_all_months_hourly_speed_profiles.png",
        "Figure 1. Hourly mean speed by direction for each available month. Records with percent observed of at least 90 are shown; all lane and station types are included.")
    cursor = insert_figure_after(cursor, "06_monday_hourly_speed_by_month.png",
        "Figure 2. Monday hourly mean speed by month and direction. Each curve averages the Mondays with qualifying records in that month; September has only two Mondays represented.")
    cursor = insert_figure_after(cursor, "07_daywise_hourly_speed_heatmap.png",
        "Figure 3. Daywise mean speed by hour across the study window. Blank columns indicate missing dates or no records passing the provisional completeness filter.")
    cursor = insert_figure_after(cursor, "08_weekday_hourly_speed_heatmap.png",
        "Figure 4. Mean speed by weekday and hour pooled across available months, directions, and lane/station types, using records with percent observed of at least 90.")

    replace_paragraph_text(conclusion,
        "The project has progressed from raw-data acquisition to a reproducible I-5 District 12 analysis dataset and a broad first-pass EDA. The strongest current evidence is a stable time-of-day pattern, a negative association between occupancy and speed, and high timestamp-key coverage for short forecasting lags. These findings establish a basis for further analysis, but they do not yet establish congestion frequencies or model performance.")
    cursor = insert_paragraph_after(conclusion,
        "Before final analysis, we should validate the station inventory, select a consistent corridor and station-type scope, define a quality and missing-data policy, and resolve the units and boundaries for a congestion label. The absent local dates and September's low completeness should be addressed explicitly in any later comparison. After those decisions, the next stage can evaluate a 15-minute forecast with chronological splits and report classification and baseline metrics.")

    # Avoid orphaned captions and keep figure blocks readable when Word paginates.
    for p in doc.paragraphs:
        if p.text.startswith("Figure "):
            p.paragraph_format.keep_with_next = False
            p.paragraph_format.keep_together = True
    save_with_template_parts(doc)
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
