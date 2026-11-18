from pathlib import Path
from zipfile import ZipFile
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph
from docx.shared import Pt

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'[Template] Project Report.docx'
OUTPUT=ROOT/'Phase_2_Project_Report.docx'

def set_text(p,text,size=13,bold=False):
    for run in list(p.runs): p._p.remove(run._r)
    r=p.add_run(text); r.font.size=Pt(size); r.bold=bold

def after(anchor,text,size=13):
    el=OxmlElement('w:p'); anchor._p.addnext(el); p=Paragraph(el,anchor._parent)
    p.style=anchor.part.document.styles['Normal']; p.paragraph_format.space_after=Pt(7); p.paragraph_format.line_spacing=1.05
    r=p.add_run(text); r.font.size=Pt(size); return p

doc=Document(TEMPLATE); ps=doc.paragraphs
set_text(ps[0],'I 5 Traffic Congestion Analysis and Short Term Speed Forecasting Phase 2 Report',20)
ps[0].alignment=WD_ALIGN_PARAGRAPH.CENTER
set_text(ps[1],'Name: Yogeshwari Pophale                         NetID: __________',14)
set_text(ps[2],'Reporting date: November 4, 2026',12)
intro,prior,dataset,milestones,results,conclusion=(ps[i] for i in (4,7,10,13,16,19))
set_text(intro,'Phase 2 established a validated District 12 I-5 mainline cohort and completed an initial 15-minute speed forecast with a chronological held-out evaluation. Across 1,843,305 eligible July-August test examples, gradient boosting achieved 1.601 mph MAE, improving on the persistence baseline at 1.747 mph. Performance is weaker for low-speed targets, and the project has not yet defined or evaluated congestion classes. The current evidence supports speed forecasting within this cohort, while further work is needed before making congestion-prediction or statewide claims.')
a=after(intro,'The project uses five-minute Caltrans PeMS observations from District 12, I-5, northbound and southbound, from January through September 2026. Phase 2 focused on verifying route station coverage, selecting a consistent mainline cohort, documenting data-quality rules, and establishing a reproducible forecasting benchmark.')
set_text(prior,'Lopez-Garcia et al. (2016) studied a 9-km Sacramento I-5 corridor using September 2013 PeMS observations at five-minute intervals. They classified traffic into four congestion states and forecast at 5-, 15-, and 30-minute horizons using a hierarchical fuzzy-rule system optimized with Genetic Algorithm and Cross-Entropy methods. The paper motivates short-horizon analysis, but its corridor, period, detector set, and congestion thresholds do not transfer directly to this study.')
a=after(prior,'The current work adapts the 15-minute horizon to a District 12 station-level speed regression task and uses chronological train, validation, and test periods. The reference paper’s printed speed and density intervals overlap, and PeMS unit and lane conventions require further reconciliation. No paper-derived congestion labels have been applied.')
a=after(a,'Reference: Lopez-Garcia, P., Onieva, E., Osaba, E., Masegosa, A. D., & Perallos, A. (2016). A hybrid method for short-term traffic congestion forecasting using genetic algorithms and cross entropy. IEEE Transactions on Intelligent Transportation Systems, 17(2), 557-567. https://doi.org/10.1109/TITS.2015.2491365.',11)
set_text(dataset,'The source is Caltrans PeMS Station 5-Minute district data. The District 12 source collection contains 175,057,116 district-wide records; filtering to freeway 5 and directions N and S retained 48,382,620 records from 715 station IDs. The retained fields include timestamp, station and roadway identifiers, lane/station type, station-level measurements, and lane-group measurements. Nine monthly compressed CSV files preserve the filtered records with descriptive field names.')
a=after(dataset,'The local collection covers 235 of 273 calendar dates from January 1 through September 30, 2026; 38 dates are absent from the supplied files. This records local acquisition coverage and does not imply that PeMS lacks those dates. The transformation reported zero malformed-width rows, and monthly checks found parseable timestamps and zero duplicate timestamp/station/direction/lane-type keys.')
a=after(a,'Direction-specific station inventory checks matched all 362 observed northbound IDs and all 353 southbound IDs to their respective District 12 PeMS inventories. The primary modeling cohort is inventory-matched mainline (ML) stations in both directions. Other types, including HOV, ramps, connectors, and collector-distributors, remain outside the primary model cohort.')
set_text(milestones,'Completed in Phase 2: validated station IDs and metadata in both directions; selected the District 12 mainline cohort; applied a documented 90% observed-data threshold and exact five-minute continuity requirement; trained an initial 15-minute speed regressor; evaluated the full eligible July-August test set; and reviewed errors by direction, month, hour, weekday/weekend, station, target-speed range, and speed-change size.')
a=after(milestones,'The chronological design uses January-May for training, June for validation, and July-August for the held-out test. Training uses a deterministic 300,000-example sample from 5,608,018 eligible windows; validation uses 75,000 of 901,020 eligible windows. The full 1,843,305 eligible test examples are evaluated. September is excluded because 85.6% of its records fall below the 90% observed threshold.')
a=after(a,'Next milestones: investigate representative low-speed and abrupt-transition errors against raw observations and nearby stations; compare at least one additional model on the same split; decide whether congestion classification remains in scope; document and validate any congestion label before training a classifier; and report class prevalence and appropriate classification metrics if labels are adopted.')
set_text(results,'The model is a HistGradientBoostingRegressor with 100 iterations and a maximum of 31 leaf nodes. Its target is average station speed in mph at t+15 minutes. Inputs available at time t include speeds at t, t-5, t-10, and t-15; flow and occupancy at t and t-5; absolute postmile; direction; and calendar/time features. Persistence predicts the t speed unchanged. Exact five-minute windows are required, inputs and target must meet the 90% observed threshold, and no measurement after t is used as an input.')
a=after(results,'On the full held-out test set, gradient boosting achieved MAE 1.601 mph, RMSE 2.858 mph, and R-squared 0.872. Persistence achieved MAE 1.747 mph, RMSE 3.198 mph, and R-squared 0.840. The model’s MAE was 8.4% lower than persistence. Northbound model MAE was 1.540 mph and southbound MAE was 1.659 mph. July and August MAE were 1.600 and 1.602 mph, respectively.')
a=after(a,'Error review shows meaningful variation by conditions. Hourly MAE was lowest around 02:00 at 1.174 mph and highest at 17:00 at 2.060 mph. Weekday MAE was 1.736 mph compared with 1.340 mph on weekends. For target speeds below 30 mph, model MAE was 6.473 mph versus 5.020 mph for persistence, so the model performed worse in that range. For target changes greater than 15 mph, model MAE was 16.89 mph versus 21.10 mph for persistence; abrupt transitions remain difficult even where the model improves on baseline.')
a=after(a,'A large observed transition at southbound station 1204886 on July 16 changed from 14.9 mph at 05:45 to 82.4 mph at 06:00, with 100% observed at both measurements. This could be a rapid recovery or a detector/aggregation issue. The percent-observed field alone cannot resolve it, so the example and nearby station behavior need review. Speed bands used in error summaries are descriptive strata and are not congestion labels.')
set_text(conclusion,'Phase 2 demonstrates that a reproducible District 12 I-5 mainline speed forecast can outperform persistence on an all-eligible July-August holdout. The validated direction-specific inventories and documented chronological evaluation provide a sound basis for additional modeling. The results answer a continuous speed forecasting question only; they do not establish congestion classification performance, statewide generalization, or performance on ramps and HOV stations.')
a=after(conclusion,'Limitations include 38 missing acquisition dates in the Jan-Sep window, reduced completeness in September, the selected 90% quality cutoff, a training sample cap, and weak model performance at low target speeds. The next phase should review unusual transitions and low-speed cases, compare another model without tuning on the test period, and settle the congestion target definition only after resolving measurement units, boundaries, and lane conventions. Any resulting classification should be evaluated separately with class prevalence, precision, recall, F1, and a confusion matrix.')
# Preserve template package parts other than edited document and its required relationships/content types.
gen=OUTPUT.with_name(OUTPUT.stem+'_generated.docx'); merged=OUTPUT.with_name(OUTPUT.stem+'_merged.docx'); doc.save(gen)
replaced={'[Content_Types].xml','word/document.xml','word/_rels/document.xml.rels'}
with ZipFile(TEMPLATE) as src, ZipFile(gen) as edit, ZipFile(merged,'w') as out:
    out.comment=src.comment; originals=set(src.namelist())
    for info in src.infolist(): out.writestr(info,edit.read(info.filename) if info.filename in replaced else src.read(info.filename))
    for info in edit.infolist():
        if info.filename not in originals: out.writestr(info,edit.read(info.filename))
merged.replace(OUTPUT); gen.unlink()
print(OUTPUT)
