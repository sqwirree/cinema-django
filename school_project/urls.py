from django.contrib import admin
from django.urls import path
from schedule import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    path('movies/', views.movie_list, name='movie_list'),
    path('sessions/<int:movie_id>/', views.session_list, name='session_list'),
    path('seats/<int:session_id>/', views.seat_selection, name='seat_selection'),
    path('reservation/', views.reservation, name='reservation'),
    path('profile/<int:viewer_id>/', views.profile, name='profile'),

    # WATCH MOVIE PAGE
    path('watch/<int:session_id>/', views.watch_session, name='watch_session'),

    # NEW — GET LIVE WATCH TIME (sync API)
    path('api/watch/<int:movie_id>/time/', views.get_group_time, name='get_group_time'),

    # ONLINE VIEWERS
    path('api/online_viewers/', views.get_online_viewers, name='get_online_viewers'),
    path('api/set_offline/', views.set_offline, name='set_offline'),

    # MOVIE PAGES
    path('movie/<int:movie_id>/', views.film_description, name='film_description'),
    path('random_movie/', views.random_movie, name='random_movie'),
    path('movie/<int:movie_id>/bookmark/', views.add_bookmark, name='add_bookmark'),
    path('movie/<int:movie_id>/rate/', views.rate_movie, name='rate_movie'),

    # FRIENDS
    path('friends/', views.friends_page, name='friends'),
    path('friends/send/<int:viewer_id>/', views.send_friend_request, name='send_friend_request'),
    path('friends/accept/<int:friendship_id>/', views.accept_friend_request, name='accept_friend_request'),
    path('friends/reject/<int:friendship_id>/', views.reject_friend_request, name='reject_friend_request'),
    path('friends/cancel/<int:friendship_id>/', views.cancel_friend_request, name='cancel_friend_request'),

    # CHAT
    path('chat/<int:friend_id>/get/', views.get_messages, name='get_messages'),
    path('chat/<int:friend_id>/send/', views.send_message, name='send_message'),
    path('chat/unread/', views.unread_counts, name='unread_counts'),

    # Online seats (cinema hall)
    path('api/online/seats/', views.online_seats, name='online_seats'),
    path('api/online/take/', views.online_take_seat, name='online_take_seat'),
    path('api/online/leave/', views.online_leave_seat, name='online_leave_seat'),

    # Global chat
    path('chat/global/get/', views.global_chat_get, name='global_chat_get'),
    path('chat/global/send/', views.global_chat_send, name='global_chat_send'),

    # Misc
    path('recommend/test/<int:movie_id>/', views.test_recommendations, name='test_recommendations'),
    path('api/track_activity/<int:movie_id>/', views.track_activity, name='track_activity'),
    path('wallet/', views.wallet_page, name='wallet'),
    path('wallet/deposit/', views.wallet_deposit, name='wallet_deposit'),
    path('confirm/ticket/<int:seat_id>/', views.confirm_ticket, name='confirm_ticket'),
    path('confirm/online/<int:movie_id>/', views.confirm_online, name='confirm_online'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
