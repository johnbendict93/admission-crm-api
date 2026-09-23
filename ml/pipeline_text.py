"""Text-classification pipeline for module 19 (NLP Call Sentiment
Analyzer) - a genuinely different shape from ml/pipeline.py's shared
tabular pipeline (ColumnTransformer over numeric+categorical columns),
since this module's only feature is free text (followups.notes). Kept in
its own file for the same reason ml/pipeline.py is separate: one place
that defines what this particular underlying model actually is."""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

RANDOM_STATE = 42


def build_text_pipeline() -> Pipeline:
    # min_df=2: ignore words appearing in only one note - mostly noise on
    # a small corpus, not real signal. ngram_range=(1,2): unigrams AND
    # bigrams, since "not interested" carries different meaning than "not"
    # and "interested" scored separately. class_weight="balanced": the 3
    # sentiment classes aren't perfectly even by design (see
    # build_followups_and_schedules' pos_w/neu_w/neg_w weighting in
    # scripts/seed_dev_fake_leads.py).
    #
    # Fixed C=1.0, not a *CV auto-tuner like ml/pipeline.py's
    # LogisticRegressionCV: that module's build_pipeline() docstring
    # documents a real degeneracy with a SINGLE categorical feature (every
    # regularization strength scores identically on ROC-AUC). TF-IDF gives
    # hundreds of numeric-valued features here, so that degeneracy doesn't
    # apply - plain, moderate L2 regularization is the standard choice for
    # a small-corpus text classifier like this one.
    vectorizer = TfidfVectorizer(min_df=2, ngram_range=(1, 2), lowercase=True)
    classifier = LogisticRegression(class_weight="balanced", max_iter=2000, C=1.0, random_state=RANDOM_STATE)
    return Pipeline(steps=[("tfidf", vectorizer), ("classify", classifier)])
