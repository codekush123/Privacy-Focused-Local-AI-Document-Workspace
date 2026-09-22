"""Generate the demo teaching materials used in the prototype video.

Run from the backend virtual environment:
    backend/.venv/Scripts/python demo_data/make_demo_data.py

All files are about one small subject (an introductory machine learning course)
so questions, quizzes, tables and slide decks generated from them make sense.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf
from docx import Document
from docx.shared import Inches
from openpyxl import Workbook
from openpyxl.styles import Font
from pptx import Presentation
from pptx.util import Inches, Pt

OUT = Path(__file__).parent

# ----------------------------------------------------------------- PDF ----
PDF_PAGES = [
    (
        "Introduction to Machine Learning - Lecture 1",
        [
            "Machine learning (ML) is the study of algorithms that improve their performance on a task through experience, "
            "usually in the form of data. Instead of writing explicit rules, we let a model discover patterns in examples.",
            "Three main paradigms are distinguished. In supervised learning the training data contains input-output pairs "
            "and the goal is to predict the output for unseen inputs. In unsupervised learning only inputs are available and "
            "the goal is to discover structure, for example clusters. In reinforcement learning an agent learns by receiving "
            "rewards for its actions.",
            "Typical supervised tasks are classification (predicting a category, e.g. spam or not spam) and regression "
            "(predicting a number, e.g. a house price). The k-nearest neighbours algorithm, decision trees, logistic "
            "regression and neural networks are common supervised methods.",
        ],
    ),
    (
        "Training, validation and testing",
        [
            "A data set is normally split into three parts. The training set is used to fit the model parameters. The "
            "validation set is used to choose hyperparameters such as the learning rate or the depth of a tree. The test "
            "set is used exactly once, at the end, to estimate how the model will perform on new data.",
            "Overfitting happens when a model learns the noise in the training data instead of the underlying pattern. "
            "Symptoms are a very low training error combined with a much higher validation error. Common remedies are "
            "collecting more data, regularisation, early stopping and simpler models.",
            "Underfitting is the opposite problem: the model is too simple to capture the pattern, so both training and "
            "validation errors stay high. The balance between the two is often described as the bias-variance trade-off.",
            "Cross-validation repeats the train/validation split several times (for example 5-fold) and averages the "
            "results, which gives a more reliable estimate when the data set is small.",
        ],
    ),
    (
        "Evaluation metrics",
        [
            "For classification the confusion matrix counts true positives (TP), false positives (FP), true negatives (TN) "
            "and false negatives (FN). Accuracy is (TP + TN) / total. Precision is TP / (TP + FP) and measures how many "
            "predicted positives are correct. Recall is TP / (TP + FN) and measures how many actual positives were found.",
            "The F1 score is the harmonic mean of precision and recall: F1 = 2 * precision * recall / (precision + recall). "
            "It is useful when the classes are imbalanced, because accuracy alone can be misleading: a model that always "
            "predicts 'healthy' is 99% accurate on a data set with 1% sick patients but is useless.",
            "For regression the mean squared error (MSE) averages the squared differences between predictions and true "
            "values, and the mean absolute error (MAE) averages the absolute differences. The coefficient of "
            "determination R^2 tells how much of the variance is explained by the model; 1.0 is perfect.",
            "Course note: the final exam is on 12 December and covers lectures 1 to 8. The verification code for this "
            "handout is ML-2026-ALPHA.",
        ],
    ),
]


BAR_DATA = [("k-NN", 0.71), ("Decision tree", 0.78), ("Random forest", 0.88), ("Neural net", 0.91)]


def _chart_page(doc) -> None:
    """A vector bar chart - no bitmap, so it can only be read by looking at the page."""
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 72), "Figure 1: Model accuracy on the course data set", fontsize=15, fontname="helv")
    left, bottom, height, width = 110, 470, 300, 90
    page.draw_line(pymupdf.Point(left, bottom), pymupdf.Point(left + 4 * width + 20, bottom), color=(0, 0, 0), width=1)
    page.draw_line(pymupdf.Point(left, bottom), pymupdf.Point(left, bottom - height), color=(0, 0, 0), width=1)
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = bottom - height * frac
        page.draw_line(pymupdf.Point(left - 4, y), pymupdf.Point(left + 4 * width + 20, y), color=(0.8, 0.8, 0.8), width=0.5)
        page.insert_text((left - 38, y + 4), f"{frac:.2f}", fontsize=9, fontname="helv")
    for i, (label, value) in enumerate(BAR_DATA):
        x0 = left + 20 + i * width
        page.draw_rect(pymupdf.Rect(x0, bottom - height * value, x0 + 55, bottom), color=(0.18, 0.33, 0.59), fill=(0.18, 0.33, 0.59))
        page.insert_text((x0 + 2, bottom + 16), label, fontsize=9, fontname="helv")
        page.insert_text((x0 + 12, bottom - height * value - 6), f"{value:.2f}", fontsize=9, fontname="helv")
    page.insert_text((60, bottom + 60), "Accuracy measured with 5-fold cross-validation on the ML-101 data set.", fontsize=10, fontname="helv")


def make_pdf() -> None:
    doc = pymupdf.open()
    for title, paragraphs in PDF_PAGES:
        page = doc.new_page(width=595, height=842)
        y = 72
        page.insert_text((60, y), title, fontsize=17, fontname="helv")
        y += 30
        for para in paragraphs:
            rect = pymupdf.Rect(60, y, 535, y + 400)
            used = page.insert_textbox(rect, para, fontsize=11, fontname="helv", lineheight=1.35)
            y += (400 - used) + 14
    _chart_page(doc)
    doc.save(OUT / "intro_machine_learning.pdf")
    doc.close()


def _chart_png() -> Path:
    """Render the bar chart to PNG so it can be embedded in DOCX/PPTX."""
    tmp = pymupdf.open()
    _chart_page(tmp)
    pix = tmp[0].get_pixmap(dpi=110, clip=pymupdf.Rect(40, 50, 560, 560))
    out = OUT / "model_accuracy_chart.png"
    pix.save(out)
    tmp.close()
    return out


# ---------------------------------------------------------------- DOCX ----
def make_docx() -> None:
    d = Document()
    d.add_heading("Neural Networks - Lecture Notes", level=0)
    d.add_paragraph("Course: Introduction to Machine Learning, Lecture 5. Reading time: about 15 minutes.")
    d.add_heading("1. The artificial neuron", level=1)
    d.add_paragraph(
        "An artificial neuron computes a weighted sum of its inputs, adds a bias term and passes the result through an "
        "activation function. With inputs x1..xn, weights w1..wn and bias b the output is a = f(w1*x1 + ... + wn*xn + b)."
    )
    d.add_paragraph("Common activation functions:", style="Intense Quote")
    for item in [
        "Sigmoid: squashes values into the range (0, 1); historically popular, but suffers from vanishing gradients.",
        "Tanh: like sigmoid but centred at zero, output range (-1, 1).",
        "ReLU (rectified linear unit): f(x) = max(0, x); cheap to compute and the default choice in modern networks.",
        "Softmax: turns a vector of scores into probabilities that sum to one; used in the output layer for classification.",
    ]:
        d.add_paragraph(item, style="List Bullet")
    d.add_heading("2. Layers and architectures", level=1)
    d.add_paragraph(
        "Neurons are organised in layers. A feed-forward network has an input layer, one or more hidden layers and an "
        "output layer. A network with many hidden layers is called a deep network, which is where the term deep learning "
        "comes from. Convolutional neural networks (CNNs) are specialised for images, recurrent networks (RNNs) and "
        "transformers for sequences such as text."
    )
    d.add_heading("3. Training with backpropagation", level=1)
    for i, step in enumerate(
        [
            "Forward pass: compute the network output for a mini-batch of training examples.",
            "Compute the loss, for example cross-entropy for classification or mean squared error for regression.",
            "Backward pass: use the chain rule to compute the gradient of the loss with respect to every weight.",
            "Update the weights with an optimiser such as stochastic gradient descent (SGD) or Adam.",
            "Repeat for many epochs until the validation loss stops improving (early stopping).",
        ],
        start=1,
    ):
        d.add_paragraph(step, style="List Number")
    d.add_heading("4. Typical hyperparameters", level=1)
    table = d.add_table(rows=1, cols=3)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "Hyperparameter", "Typical value", "Effect"
    for row in [
        ("Learning rate", "0.001 - 0.1", "Step size of each weight update; too high diverges, too low is slow"),
        ("Batch size", "32 - 256", "Number of examples per gradient step"),
        ("Epochs", "10 - 100", "Number of passes over the training data"),
        ("Dropout", "0.2 - 0.5", "Fraction of neurons randomly disabled during training to reduce overfitting"),
    ]:
        cells = table.add_row().cells
        for c, v in zip(cells, row):
            c.text = v
    d.add_heading("5. Measured accuracy", level=1)
    d.add_paragraph("The chart below compares the accuracy of the models discussed in this course.")
    d.add_picture(str(_chart_png()), width=Inches(5.5))
    d.add_heading("6. Summary", level=1)
    d.add_paragraph(
        "A neural network is a stack of simple neurons whose weights are learned by minimising a loss with gradient "
        "descent. ReLU activations, mini-batch training and dropout are standard practice. The verification code for "
        "these notes is NN-2026-BETA."
    )
    d.save(OUT / "neural_networks_lecture.docx")


# ---------------------------------------------------------------- PPTX ----
def make_pptx() -> None:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "Decision Trees and Random Forests"
    s.placeholders[1].text = "Introduction to Machine Learning - Lecture 3"
    slides = [
        ("What is a decision tree?", [
            "A flowchart-like model: each internal node tests one feature",
            "Each branch is an outcome of the test, each leaf is a prediction",
            "Works for both classification and regression",
            "Easy to interpret and visualise",
        ]),
        ("How is a tree built?", [
            "Greedy top-down splitting (CART algorithm)",
            "Choose the split that best separates the classes",
            "Impurity measures: Gini index and entropy (information gain)",
            "Stop when nodes are pure, too small, or the maximum depth is reached",
        ]),
        ("Strengths and weaknesses", [
            "+ No feature scaling needed, handles mixed data types",
            "+ Interpretable: the path from root to leaf explains the prediction",
            "- A single deep tree overfits easily",
            "- Small changes in data can produce a very different tree (high variance)",
        ]),
        ("Random forests", [
            "An ensemble of many decision trees",
            "Each tree is trained on a bootstrap sample of the data (bagging)",
            "At each split only a random subset of features is considered",
            "Final prediction: majority vote (classification) or average (regression)",
            "Reduces variance dramatically compared to a single tree",
        ]),
        ("Results", [
            "Random forests and neural networks performed best",
            "See the accuracy chart on this slide",
        ]),
        ("Key takeaways", [
            "Trees split data with simple feature tests",
            "Gini and entropy measure how good a split is",
            "Forests combine hundreds of trees for robust predictions",
            "Verification code for this deck: TREE-2026-GAMMA",
        ]),
    ]
    chart_png = _chart_png()
    for title, bullets in slides:
        sl = prs.slides.add_slide(prs.slide_layouts[1])
        sl.shapes.title.text = title
        if title == "Results":
            sl.shapes.add_picture(str(chart_png), Inches(7.2), Inches(1.6), height=Inches(4.2))
        tf = sl.placeholders[1].text_frame
        tf.text = bullets[0]
        for b in bullets[1:]:
            tf.add_paragraph().text = b
        for p in tf.paragraphs:
            p.font.size = Pt(22)
        sl.notes_slide.notes_text_frame.text = f"Speaker notes for '{title}'."
    prs.save(OUT / "decision_trees_slides.pptx")


# ------------------------------------------------------------ CSV/XLSX ----
STUDENTS = [
    ("S001", "Aino Virtanen", "ML-101", 78, 85, 91, "Finland"),
    ("S002", "Li Wei", "ML-101", 92, 88, 95, "China"),
    ("S003", "Omar Haddad", "ML-101", 65, 70, 58, "Jordan"),
    ("S004", "Anna Petrova", "ML-101", 88, 79, 84, "Russia"),
    ("S005", "James Miller", "ML-101", 54, 61, 49, "United Kingdom"),
    ("S006", "Sofia Rossi", "ML-101", 97, 94, 99, "Italy"),
    ("S007", "Kenji Sato", "ML-101", 72, 68, 75, "Japan"),
    ("S008", "Maria Silva", "ML-101", 81, 90, 86, "Brazil"),
    ("S009", "Elias Koskinen", "ML-101", 43, 55, 60, "Finland"),
    ("S010", "Fatima Al-Sayed", "ML-101", 89, 92, 90, "Egypt"),
    ("S011", "Lucas Martin", "ML-101", 70, 74, 66, "France"),
    ("S012", "Priya Sharma", "ML-101", 95, 91, 93, "India"),
]
HEADERS = ["student_id", "name", "course", "assignment_1", "assignment_2", "exam", "country"]


def make_csv_xlsx() -> None:
    import csv

    with (OUT / "student_results.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADERS)
        w.writerows(STUDENTS)

    wb = Workbook()
    ws = wb.active
    ws.title = "Results"
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for row in STUDENTS:
        ws.append(list(row))
    ws2 = wb.create_sheet("Grading scale")
    ws2.append(["Grade", "Minimum final score", "Description"])
    for c in ws2[1]:
        c.font = Font(bold=True)
    for r in [("5", 90, "Excellent"), ("4", 80, "Very good"), ("3", 70, "Good"), ("2", 60, "Satisfactory"), ("1", 50, "Sufficient"), ("0", 0, "Fail")]:
        ws2.append(list(r))
    ws3 = wb.create_sheet("Weights")
    ws3.append(["Component", "Weight"])
    ws3.append(["assignment_1", 0.25])
    ws3.append(["assignment_2", 0.25])
    ws3.append(["exam", 0.5])
    wb.save(OUT / "student_results.xlsx")


# ---------------------------------------------------------------- HTML ----
def make_html() -> None:
    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>ML Glossary - Introduction to Machine Learning</title>
<style>body{font-family:sans-serif}</style><script>console.log('not executed')</script></head>
<body>
<nav><a href="/">Home</a> | <a href="/courses">Courses</a></nav>
<main>
<h1>Machine Learning Glossary</h1>
<p>Short definitions of terms used in the Introduction to Machine Learning course.</p>
<h2>Terms</h2>
<dl>
<dt>Feature</dt><dd>An individual measurable property of the data, e.g. the age of a customer.</dd>
<dt>Label</dt><dd>The value a supervised model is trained to predict.</dd>
<dt>Epoch</dt><dd>One complete pass of the training algorithm over the whole training set.</dd>
<dt>Gradient descent</dt><dd>An optimisation method that repeatedly moves the parameters in the direction that reduces the loss most.</dd>
<dt>Regularisation</dt><dd>Any technique that penalises model complexity to reduce overfitting, e.g. L2 weight decay.</dd>
<dt>Embedding</dt><dd>A learned dense vector representation of a discrete item such as a word.</dd>
</dl>
<h2>Cheat sheet</h2>
<table>
<tr><th>Task</th><th>Typical algorithm</th><th>Typical metric</th></tr>
<tr><td>Binary classification</td><td>Logistic regression</td><td>F1 score</td></tr>
<tr><td>Regression</td><td>Linear regression</td><td>Mean squared error</td></tr>
<tr><td>Clustering</td><td>k-means</td><td>Silhouette score</td></tr>
</table>
<p>Verification code for this page: GLOSS-2026-DELTA.</p>
</main>
<footer>© Example University - this footer is navigation noise</footer>
</body></html>"""
    (OUT / "ml_glossary.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    make_pdf()
    make_docx()
    make_pptx()
    make_csv_xlsx()
    make_html()
    print("Demo data written to", OUT)
