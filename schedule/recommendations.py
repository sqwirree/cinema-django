from django.db.models import Avg
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .models import Movie, MovieActivity, Rating
import numpy as np


# ============================================================
# === 1. Сходство по жанрам ==================================
# ============================================================
def genre_similarity(base_movie, candidate):
    base_genres = set(base_movie.genres.values_list('id', flat=True))
    candidate_genres = set(candidate.genres.values_list('id', flat=True))

    if not base_genres or not candidate_genres:
        return 0.0

    intersection = len(base_genres & candidate_genres)
    union = len(base_genres | candidate_genres)
    return intersection / union


# ============================================================
# === 2. TF-IDF кэш ==========================================
# ============================================================
_tfidf_cache = {"vectorizer": None, "matrix": None, "movie_ids": None}

def _ensure_tfidf_cache():
    movies = Movie.objects.all()
    ids = [m.id for m in movies]
    texts = [
        (m.full_description or "") + " " + (m.short_description or "")
        for m in movies
    ]
    vectorizer = TfidfVectorizer(stop_words='english', max_features=5000)
    matrix = vectorizer.fit_transform(texts)

    _tfidf_cache.update({
        "vectorizer": vectorizer,
        "matrix": matrix,
        "movie_ids": ids
    })


def description_similarity(base_movie, candidate):
    if _tfidf_cache["matrix"] is None:
        _ensure_tfidf_cache()

    try:
        base_idx = _tfidf_cache["movie_ids"].index(base_movie.id)
        cand_idx = _tfidf_cache["movie_ids"].index(candidate.id)
    except ValueError:
        _ensure_tfidf_cache()
        base_idx = _tfidf_cache["movie_ids"].index(base_movie.id)
        cand_idx = _tfidf_cache["movie_ids"].index(candidate.id)

    sim = cosine_similarity(
        _tfidf_cache["matrix"][base_idx],
        _tfidf_cache["matrix"][cand_idx]
    )[0][0]

    return float(sim)


# ============================================================
# === 3. Активность пользователя ==============================
# ============================================================
def recent_activity_score(viewer, candidate):
    act = MovieActivity.objects.filter(
        viewer=viewer,
        movie=candidate
    ).first()

    if not act:
        return 0.0

    score = 0.0
    # Максимум 5 минут = полный балл
    score += min(act.time_spent / 300, 1.0) * 0.6
    if act.watched_trailer:
        score += 0.25
    if act.watched_movie:
        score += 0.15

    return min(score, 1.0)


# ============================================================
# === 4. Основная функция гибридных рекомендаций ==============
# ============================================================
def hybrid_recommendations(viewer, limit=10):
    """
    Гибридная система рекомендаций:
    1. Основной приоритет — похожие по описанию и жанрам к фильмам,
       которые пользователь оценил высоко.
    2. Низкие оценки уменьшают вес схожих фильмов.
    3. Активность повышает вес фильмов, которые пользователь не оценил.
    """
    all_movies = list(Movie.objects.all())
    ratings = Rating.objects.filter(viewer=viewer)
    rated_movies = {r.movie: r.score for r in ratings}
    scored = []

    for candidate in all_movies:
        if candidate in rated_movies:
            continue

        total_weight = 0.0
        sim_sum = 0.0

        # === 1. Сравнение с оценёнными фильмами ===
        for rated_movie, score in rated_movies.items():
            # шкала [-1, 1]: низкая оценка → -1, высокая → +1
            mood = (score - 5) / 5.0
            genre_sim = genre_similarity(rated_movie, candidate)
            desc_sim = description_similarity(rated_movie, candidate)

            # если низкая оценка — уменьшаем схожесть
            base_sim = (genre_sim * 0.45 + desc_sim * 0.55) * mood
            sim_sum += base_sim
            total_weight += abs(mood)

        # нормализация
        if total_weight > 0:
            preference_score = sim_sum / total_weight
        else:
            preference_score = 0.0

        # === 2. Добавляем влияние активности ===
        activity_score = recent_activity_score(viewer, candidate)

        # === 3. Итоговый скор ===
        # Приоритет по описанию и жанрам (70%), активность (30%)
        final_score = 0.7 * preference_score + 0.3 * activity_score

        scored.append((candidate, final_score))

    # === 4. Если нет оценок — fallback ===
    if not rated_movies:
        scored = []
        for movie in all_movies:
            activity_score = recent_activity_score(viewer, movie)
            scored.append((movie, activity_score))

    # === 5. Сортировка и результат ===
    scored.sort(key=lambda x: x[1], reverse=True)
    return [m for m, _ in scored[:limit]]