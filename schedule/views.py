from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseForbidden, JsonResponse
from django.conf import settings
from django.db import models
from django.db.models import Q, Count
from django.contrib import messages
from django.utils import timezone
from django.core.cache import cache 

import random
from decimal import Decimal

from .models import *
from .forms import CustomUserCreationForm, AvatarUpdateForm
from .recommendations import hybrid_recommendations


def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()

            viewer = Viewer.objects.create(
                user=user,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                age=user.age,
                gender=user.gender,
                avatar=user.avatar
            )

            wallet = Wallet.objects.create(viewer=viewer)

            login(request, user)
            messages.success(request, f"Ласкаво просимо, {user.first_name}")
            return redirect("home")
    else:
        form = CustomUserCreationForm()

    return render(request, "register.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            return redirect("home")
        else:
            return render(request, "login.html", {"error": "Невірний email або пароль"})
    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required(login_url='login')
def movie_list(request):
    viewer = request.user.viewer
    movies = Movie.objects.all()

    recommendations = hybrid_recommendations(viewer, limit=5)

    return render(request, 'movie_list.html', {
        'movies': movies,
        'recommendations': recommendations,
        'viewer': viewer
    })


def home(request):
    return render(request, 'home.html')


def session_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    sessions = Session.objects.filter(movie=movie)
    return render(request, 'session_list.html', {'movie': movie, 'sessions': sessions})


@login_required
def seat_selection(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    seats = session.seats.all().order_by('row', 'column')

    seat_rows = []
    current_row = []
    last_row = None
    for seat in seats:
        if last_row is None or seat.row != last_row:
            if current_row:
                seat_rows.append(current_row)
            current_row = []
            last_row = seat.row
        current_row.append(seat)
    if current_row:
        seat_rows.append(current_row)

    if request.method == 'POST':
        seat_id = request.POST.get('seat_id')
        seat = get_object_or_404(Seat, id=seat_id)

        if not hasattr(request.user, 'viewer'):
            return HttpResponseForbidden("Ви повинні бути глядачем")

        viewer = request.user.viewer

        if seat.is_reserved:
            return redirect('viewer_sessions', viewer_id=seat.viewer.id)

        if Seat.objects.filter(session=session, viewer=viewer).exists():
            return redirect('viewer_sessions', viewer_id=viewer.id)

        seat.is_reserved = True
        seat.viewer = viewer
        seat.save()

        return redirect('reservation')

    return render(request, 'seat_selection.html', {
        'session': session,
        'seat_rows': seat_rows
    })


@login_required
def reservation(request):
    return render(request, 'reservation.html')


@login_required
def viewer_sessions(request, viewer_id):
    viewer = get_object_or_404(Viewer, id=viewer_id)
    sessions = viewer.sessions
    return render(request, 'viewer_sessions.html', {'viewer': viewer, 'sessions': sessions})


@login_required
def profile(request, viewer_id):
    viewer = get_object_or_404(Viewer, id=viewer_id)
    user = request.user
    can_edit = viewer.user == user
    me = request.user.viewer

    if request.method == 'POST' and can_edit:
        form = AvatarUpdateForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            viewer.avatar = user.avatar
            viewer.save(update_fields=['avatar'])
            return redirect('profile', viewer_id=viewer.id)
    else:
        form = AvatarUpdateForm(instance=user)

    bookmarks = viewer.bookmarks.select_related('movie')
    friend_status = _friendship_status(me, viewer)

    friends_list = Viewer.objects.filter(
        models.Q(friendship_from__to_viewer=viewer, friendship_from__status='accepted') |
        models.Q(friendship_to__from_viewer=viewer, friendship_to__status='accepted')
    ).distinct()

    return render(request, 'profile.html', {
        'viewer': viewer,
        'form': form,
        'sessions': viewer.sessions,
        'bookmarks': bookmarks,
        'can_edit': can_edit,
        'friend_status': friend_status,
        'friends_list': friends_list,
    })


@login_required
def watch_session(request, session_id):
    movie = get_object_or_404(Movie, id=session_id)
    viewer = request.user.viewer

    if OnlineSeat.objects.count() == 0:
        seats = [
            OnlineSeat(row=r, column=c)
            for r in range(1, 7)
            for c in range(1, 11)
        ]
        OnlineSeat.objects.bulk_create(seats)

    viewer.is_online = True
    viewer.save(update_fields=['is_online'])

    my_seat = OnlineSeat.objects.filter(viewer=viewer).first()

    if not my_seat:
        free_seat = OnlineSeat.objects.filter(is_reserved=False).first()
        if free_seat:
            free_seat.is_reserved = True
            free_seat.viewer = viewer
            free_seat.save(update_fields=['is_reserved', 'viewer'])
        else:
            print("⚠️ Немає вільних місць для:", viewer)

    return render(request, 'watch_session.html', {
        'movie': movie,
        'online_viewers': Viewer.objects.filter(is_online=True)
    })

def get_group_time(request, movie_id):
    """
    Возвращает текущее групповое время просмотра фильма в секундах.
    Стартовое время хранится в кэше и создаётся только один раз.
    """
    movie = get_object_or_404(Movie, id=movie_id)

    cache_key = f"live_movie_{movie_id}_start"
    started_at = cache.get(cache_key)

    # Если ещё никто не смотрел этот фильм онлайн – считаем, что стартуем сейчас
    if started_at is None:
        started_at = timezone.now()
        # таймаут None = хранить, пока живёт процесс (для dev хватает)
        cache.set(cache_key, started_at, timeout=None)

    delta = timezone.now() - started_at
    pos = delta.total_seconds()
    if pos < 0:
        pos = 0

    return JsonResponse({
        "ok": True,
        "position": round(pos, 1)
    })

@login_required
def get_online_viewers(request):
    online_viewers = Viewer.objects.filter(is_online=True).values('id', 'first_name', 'avatar')
    data = []
    for v in online_viewers:
        data.append({
            'id': v['id'],
            'first_name': v['first_name'],
            'avatar_url': request.build_absolute_uri(settings.MEDIA_URL + v['avatar'])
        })
    return JsonResponse({'viewers': data})


@csrf_exempt
@login_required
def set_offline(request):
    viewer = request.user.viewer
    viewer.is_online = False
    viewer.save()
    return JsonResponse({'status': 'ok'})


@login_required
def film_description(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    viewer = request.user.viewer
    first_session = movie.session_set.first()

    bookmark = Bookmark.objects.filter(viewer=viewer, movie=movie).first()
    rating = Rating.objects.filter(viewer=viewer, movie=movie).first()
    activity = MovieActivity.objects.filter(viewer=viewer, movie=movie).first()

    avg_rating = movie.ratings.aggregate(models.Avg('score'))['score__avg']
    if avg_rating:
        avg_rating = round(avg_rating, 1)

    return render(request, 'film_description.html', {
        'movie': movie,
        'first_session': first_session,
        'bookmark': bookmark,
        'rating': rating,
        'activity': activity,
        'avg_rating': avg_rating,
        'Bookmark': Bookmark
    })


@login_required(login_url='login')
def random_movie(request):
    movies = list(Movie.objects.all())
    if not movies:
        return redirect('movie_list')

    movie = random.choice(movies)
    return redirect('film_description', movie_id=movie.id)


def _is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest' or \
           'application/json' in request.headers.get('Accept', '')


@require_POST
@login_required
def add_bookmark(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    viewer = request.user.viewer
    status = request.POST.get('status')

    if status == 'nothing':
        Bookmark.objects.filter(viewer=viewer, movie=movie).delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'ok': True,
                'in_bookmarks': False,
                'status_display': '———',
            })
        return redirect('film_description', movie_id=movie.id)

    valid = dict(Bookmark.STATUS_CHOICES).keys()
    if status not in valid:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Некоректний статус'}, status=400)
        return redirect('film_description', movie_id=movie.id)

    bookmark, created = Bookmark.objects.update_or_create(
        viewer=viewer, movie=movie, defaults={'status': status}
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'in_bookmarks': True,
            'status': bookmark.status,
            'status_display': bookmark.get_status_display(),
        })

    return redirect('film_description', movie_id=movie.id)


@require_POST
@login_required
def rate_movie(request, movie_id):
    viewer = request.user.viewer
    movie = get_object_or_404(Movie, id=movie_id)
    score_raw = request.POST.get('score')

    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        score = None

    if not score or not (1 <= score <= 10):
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'error': 'Оцінка повинна бути від 1 до 10'}, status=400)
        return redirect('film_description', movie_id=movie.id)

    Rating.objects.update_or_create(
        viewer=viewer, movie=movie, defaults={'score': score}
    )

    avg = movie.ratings.aggregate(models.Avg('score'))['score__avg']
    avg_rating = round(avg, 1) if avg else None

    if _is_ajax(request):
        return JsonResponse({'ok': True, 'score': score, 'avg_rating': avg_rating})

    return redirect('film_description', movie_id=movie.id)


def _friendship_status(me: Viewer, other: Viewer) -> str:
    if me.id == other.id:
        return 'self'
    pair = Friendship.objects.filter(
        Q(from_viewer=me, to_viewer=other) | Q(from_viewer=other, to_viewer=me)
    ).order_by('-created_at').first()
    if not pair:
        return 'none'
    if pair.status == 'accepted':
        return 'friends'
    if pair.status == 'pending' and pair.from_viewer_id == me.id:
        return 'outgoing'
    if pair.status == 'pending' and pair.to_viewer_id == me.id:
        return 'incoming'
    return 'none'


@login_required
def friends_page(request):
    me = request.user.viewer

    friends_qs = Viewer.objects.filter(
        Q(friendship_from__to_viewer=me, friendship_from__status='accepted') |
        Q(friendship_to__from_viewer=me, friendship_to__status='accepted')
    ).distinct().select_related('user')

    incoming_qs = Friendship.objects.filter(
        to_viewer=me, status='pending'
    ).select_related('from_viewer__user')

    outgoing_qs = Friendship.objects.filter(
        from_viewer=me, status='pending'
    ).select_related('to_viewer__user')

    active_id = request.GET.get('open')
    active_friend = None
    if active_id:
        try:
            candidate = Viewer.objects.get(pk=active_id)
            if _friendship_status(me, candidate) == 'friends':
                active_friend = candidate
        except Viewer.DoesNotExist:
            active_friend = None

    return render(request, 'friends.html', {
        'friends': friends_qs,
        'incoming': incoming_qs,
        'outgoing': outgoing_qs,
        'active_friend': active_friend,
    })


@login_required
@require_POST
def send_friend_request(request, viewer_id):
    me = request.user.viewer
    to = get_object_or_404(Viewer, id=viewer_id)

    if me.id == to.id:
        messages.error(request, 'Неможливо додати самого себе.')
        return redirect('profile', viewer_id=viewer_id)

    if _friendship_status(me, to) == 'friends':
        return redirect('profile', viewer_id=viewer_id)

    incoming = Friendship.objects.filter(from_viewer=to, to_viewer=me, status='pending').first()
    if incoming:
        incoming.status = 'accepted'
        incoming.save(update_fields=['status'])
        messages.success(request, f'Тепер ви друзі з {to.first_name or to.email}.')
        return redirect('profile', viewer_id=viewer_id)

    obj, created = Friendship.objects.get_or_create(
        from_viewer=me, to_viewer=to,
        defaults={'status': 'pending'}
    )
    if not created and obj.status == 'rejected':
        obj.status = 'pending'
        obj.save(update_fields=['status'])

    messages.success(request, 'Запит у друзі відправлено.')
    return redirect('profile', viewer_id=viewer_id)


@login_required
@require_POST
def accept_friend_request(request, friendship_id):
    me = request.user.viewer
    fr = get_object_or_404(Friendship, id=friendship_id, to_viewer=me, status='pending')
    fr.status = 'accepted'
    fr.save(update_fields=['status'])
    messages.success(request, f'Запит від {fr.from_viewer.first_name or fr.from_viewer.email} прийнято.')
    return redirect('friends')


@login_required
@require_POST
def reject_friend_request(request, friendship_id):
    me = request.user.viewer
    fr = get_object_or_404(Friendship, id=friendship_id, to_viewer=me, status='pending')
    fr.status = 'rejected'
    fr.save(update_fields=['status'])
    messages.info(request, f'Запит від {fr.from_viewer.first_name or fr.from_viewer.email} відхилено.')
    return redirect('friends')


@login_required
@require_POST
def cancel_friend_request(request, friendship_id):
    me = request.user.viewer
    fr = get_object_or_404(Friendship, id=friendship_id, from_viewer=me, status='pending')
    fr.delete()
    messages.info(request, 'Вихідний запит скасовано.')
    return redirect('friends')


@login_required
@require_GET
def get_messages(request, friend_id):
    me = request.user.viewer
    friend = get_object_or_404(Viewer, id=friend_id)

    from .models import Friendship
    if not Friendship.objects.filter(
        models.Q(from_viewer=me, to_viewer=friend, status='accepted') |
        models.Q(from_viewer=friend, to_viewer=me, status='accepted')
    ).exists():
        return JsonResponse({'ok': False, 'error': 'not_friends'}, status=403)

    messages_qs = Message.objects.filter(
        models.Q(sender=me, receiver=friend) | models.Q(sender=friend, receiver=me)
    ).order_by('timestamp')

    Message.objects.filter(sender=friend, receiver=me, is_read=False).update(is_read=True)

    data = [
        {
            'sender': msg.sender.first_name or msg.sender.email,
            'text': msg.text,
            'time': msg.timestamp.strftime('%H:%M'),
            'is_me': msg.sender_id == me.id,
        }
        for msg in messages_qs
    ]
    return JsonResponse({'ok': True, 'messages': data})


@login_required
@require_POST
def send_message(request, friend_id):
    me = request.user.viewer
    friend = get_object_or_404(Viewer, id=friend_id)
    text = request.POST.get('text', '').strip()

    if not text:
        return JsonResponse({'ok': False, 'error': 'empty'})

    if not Friendship.objects.filter(
        models.Q(from_viewer=me, to_viewer=friend, status='accepted') |
        models.Q(from_viewer=friend, to_viewer=me, status='accepted')
    ).exists():
        return JsonResponse({'ok': False, 'error': 'not_friends'}, status=403)

    Message.objects.create(sender=me, receiver=friend, text=text, timestamp=timezone.now())
    return JsonResponse({'ok': True})


@login_required
def unread_counts(request):
    me = request.user.viewer
    unread = Message.objects.filter(receiver=me, is_read=False) \
        .values('sender') \
        .annotate(count=Count('id'))

    data = {str(item['sender']): item['count'] for item in unread}
    return JsonResponse({'ok': True, 'unread': data})


@login_required
@require_GET
def online_seats(request):
    seats = OnlineSeat.objects.select_related('viewer').order_by('row', 'column')
    data = []
    for s in seats:
        item = {
            'id': s.id,
            'row': s.row,
            'column': s.column,
            'is_reserved': s.is_reserved,
            'viewer_id': s.viewer_id,
            'viewer_name': None,
            'avatar_url': None,
            'is_me': False,
        }
        if s.viewer:
            item['is_me'] = (request.user.viewer.id == s.viewer.id)
            item['viewer_name'] = s.viewer.first_name or "Глядач"
            avatar_path = s.viewer.avatar.name if s.viewer.avatar else None
            if avatar_path:
                item['avatar_url'] = request.build_absolute_uri(settings.MEDIA_URL + avatar_path)
        data.append(item)
    return JsonResponse({'ok': True, 'seats': data})


@login_required
@require_POST
def online_take_seat(request):
    viewer = request.user.viewer
    seat_id = request.POST.get('seat_id')
    seat = get_object_or_404(OnlineSeat, id=seat_id)

    OnlineSeat.objects.filter(viewer=viewer).update(is_reserved=False, viewer=None)

    if seat.is_reserved and seat.viewer_id != viewer.id:
        return JsonResponse({'ok': False, 'error': 'taken'}, status=409)

    seat.is_reserved = True
    seat.viewer = viewer
    seat.save(update_fields=['is_reserved', 'viewer'])
    return JsonResponse({'ok': True})


@csrf_exempt
@login_required
@require_POST
def online_leave_seat(request):
    viewer = request.user.viewer
    OnlineSeat.objects.filter(viewer=viewer).update(is_reserved=False, viewer=None)
    return JsonResponse({'ok': True})


@login_required
@require_GET
def global_chat_get(request):
    me = request.user.viewer
    msgs = GlobalChatMessage.objects.select_related('sender', 'receiver').order_by('-timestamp')[:80]

    data = []
    for m in reversed(msgs):
        if not m.is_private or m.sender == me or m.receiver == me:
            data.append({
                'sender': m.sender.first_name or "Глядач",
                'receiver': m.receiver.first_name if m.receiver else None,
                'avatar': request.build_absolute_uri(settings.MEDIA_URL + m.sender.avatar.name),
                'text': m.text,
                'time': m.timestamp.strftime('%H:%M'),
                'is_private': m.is_private,
            })
    return JsonResponse({'ok': True, 'messages': data})


@login_required
@require_POST
def global_chat_send(request):
    me = request.user.viewer
    text = request.POST.get('text', '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'empty'})

    receiver = None
    is_private = False
    if text.startswith('!private '):
        parts = text.split(maxsplit=2)
        if len(parts) >= 3:
            _, name, msg = parts
            receiver = Viewer.objects.filter(first_name__iexact=name).first()
            if receiver:
                is_private = True
                text = msg
    GlobalChatMessage.objects.create(sender=me, receiver=receiver, text=text, is_private=is_private)
    return JsonResponse({'ok': True})


@login_required
def test_recommendations(request, movie_id):
    viewer = request.user.viewer
    movie = get_object_or_404(Movie, id=movie_id)
    recs = hybrid_recommendations(viewer, movie)
    titles = [m.title for m in recs]
    return JsonResponse({'ok': True, 'recommendations': titles})


@csrf_exempt
@login_required
@require_POST
def track_activity(request, movie_id):
    viewer = request.user.viewer
    movie = get_object_or_404(Movie, id=movie_id)

    data = request.POST
    time_spent = float(data.get('time_spent', 0))
    watched_trailer = data.get('watched_trailer') == 'true'
    watched_movie = data.get('watched_movie') == 'true'

    act, _ = MovieActivity.objects.get_or_create(viewer=viewer, movie=movie)
    act.time_spent += time_spent
    act.watched_trailer = act.watched_trailer or watched_trailer
    act.watched_movie = act.watched_movie or watched_movie
    act.save(update_fields=['time_spent', 'watched_trailer', 'watched_movie', 'last_visit'])

    return JsonResponse({'ok': True})


@login_required
def wallet_page(request):
    viewer = request.user.viewer
    wallet, _ = Wallet.objects.get_or_create(viewer=viewer)
    transactions = wallet.transactions.all()

    if request.method == 'POST':
        code_input = request.POST.get('code', '').strip().upper()

        promo = PromoCode.objects.filter(code__iexact=code_input).first()
        if not promo:
            messages.error(request, "Такого промокоду не існує.")
            return redirect('wallet')

        valid, error = promo.is_valid_for(viewer)
        if not valid:
            messages.error(request, error)
            return redirect('wallet')

        wallet.balance += promo.amount
        wallet.save(update_fields=['balance'])

        promo.used_by.add(viewer)
        promo.used_count += 1
        promo.save(update_fields=['used_count'])

        Transaction.objects.create(
            wallet=wallet,
            type='promo',
            amount=promo.amount,
            description=f"Поповнення промокодом {promo.code}"
        )

        messages.success(request, f"Баланс поповнено на {promo.amount}₴!")
        return redirect('wallet')

    return render(request, 'wallet.html', {
        'wallet': wallet,
        'transactions': transactions
    })


@login_required
def wallet_deposit(request):
    viewer = request.user.viewer
    wallet, _ = Wallet.objects.get_or_create(viewer=viewer)

    ALLOWED_AMOUNTS = [50, 100, 250, 500]

    if request.method == 'POST':
        try:
            amount = int(request.POST.get('amount'))
        except (TypeError, ValueError):
            messages.error(request, "Некоректна сума.")
            return redirect('wallet_deposit')

        if amount not in ALLOWED_AMOUNTS:
            messages.error(request, "Ця сума недоступна для поповнення.")
            return redirect('wallet_deposit')

        wallet.balance += amount
        wallet.save(update_fields=['balance'])

        Transaction.objects.create(
            wallet=wallet,
            type='deposit',
            amount=amount,
            description=f"Поповнення балансу на {amount}₴"
        )

        messages.success(request, f"Баланс успішно поповнено на {amount}₴!")
        return redirect('wallet')

    return render(request, 'wallet_deposit.html', {
        'wallet': wallet,
        'allowed': ALLOWED_AMOUNTS
    })


@login_required
def confirm_online(request, movie_id):
    viewer = request.user.viewer
    movie = get_object_or_404(Movie, id=movie_id)
    wallet, _ = Wallet.objects.get_or_create(viewer=viewer)
    ONLINE_PRICE = Decimal('80.00')

    if MovieActivity.objects.filter(viewer=viewer, movie=movie, watched_movie=True).exists():
        messages.info(request, "Ви вже маєте доступ до онлайн-перегляду 🎬")
        return redirect('film_description', movie_id=movie.id)

    if request.method == 'POST':
        if wallet.balance < ONLINE_PRICE:
            messages.error(request, "Недостатньо коштів 💸.")
            return redirect('wallet_deposit')

        wallet.balance -= ONLINE_PRICE
        wallet.save(update_fields=['balance'])
        Transaction.objects.create(
            wallet=wallet,
            type='spend',
            amount=ONLINE_PRICE,
            description=f"Покупка онлайн-доступу до '{movie.title}'"
        )

        MovieActivity.objects.update_or_create(
            viewer=viewer, movie=movie,
            defaults={'watched_movie': True}
        )

        messages.success(request, f"Доступ до онлайн-перегляду '{movie.title}' надано 🎥")
        return redirect('film_description', movie_id=movie.id)

    return render(request, 'confirm_online.html', {
        'movie': movie,
        'price': ONLINE_PRICE,
        'viewer': viewer,
        'wallet': wallet,
    })


@login_required
def confirm_ticket(request, seat_id):
    seat = get_object_or_404(Seat, id=seat_id)
    session = seat.session
    viewer = request.user.viewer
    wallet, _ = Wallet.objects.get_or_create(viewer=viewer)

    ticket_price = Decimal(str(session.price))

    if seat.is_reserved:
        messages.error(request, "Це місце вже зайняте.")
        return redirect('seat_selection', session_id=session.id)

    if request.method == 'POST':
        if wallet.balance < ticket_price:
            messages.error(request, "Недостатньо коштів 💸. Поповніть баланс.")
            return redirect('wallet_deposit')

        wallet.balance -= ticket_price
        wallet.save(update_fields=['balance'])

        Transaction.objects.create(
            wallet=wallet,
            type='spend',
            amount=ticket_price,
            description=f"Покупка квитка на '{session.movie.title}' (ряд {seat.row}, місце {seat.column})"
        )

        seat.is_reserved = True
        seat.viewer = viewer
        seat.save(update_fields=['is_reserved', 'viewer'])

        messages.success(request, "Квиток успішно придбано! 🎟")
        return redirect('reservation')

    return render(request, 'confirm_ticket.html', {
        'seat': seat,
        'session': session,
        'movie': session.movie,
        'viewer': viewer,
        'wallet': wallet,
    })
