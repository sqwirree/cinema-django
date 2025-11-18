from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone



class CustomUserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email є обов'язковим")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(
        max_length=10,
        choices=[("male", "Чоловічий"), ("female", "Жіночий")],
        null=True,
        blank=True
    )
    avatar = models.ImageField(
        upload_to="profile_images/",
        default="profile_images/standart_avatar.png"
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return f"{self.email}"


class Genre(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Movie(models.Model):
    title = models.CharField(max_length=255)
    short_description = models.TextField(verbose_name="Короткий опис", blank=True, null=True)
    full_description = models.TextField(verbose_name="Повний опис", blank=True, null=True)
    genres = models.ManyToManyField('Genre', related_name='movies', verbose_name="Жанри")
    release_year = models.IntegerField()
    image = models.ImageField(upload_to='movie_images/', null=True, blank=True)

    has_online_viewing = models.BooleanField(default=False, verbose_name="Є онлайн перегляд")
    video_file = models.FileField(
        upload_to='movie_videos/',
        null=True,
        blank=True,
        verbose_name="Відео для онлайн перегляду"
    )

    has_trailer = models.BooleanField(default=False, verbose_name="Є трейлер")
    trailer_file = models.FileField(
        upload_to='movie_trailers/',
        null=True,
        blank=True,
        verbose_name="Файл трейлера"
    )

    @property
    def average_rating(self):
        ratings = self.ratings.all()
        if ratings.exists():
            return round(sum(r.score for r in ratings) / ratings.count(), 1)
        return None

    def __str__(self):
        return self.title


class Hall(models.Model):
    name = models.CharField(max_length=100)
    rows = models.PositiveIntegerField()
    seats_per_row = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.name} ({self.rows}x{self.seats_per_row})"


class Session(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE)
    datetime = models.DateTimeField()
    price = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=120.00,
        verbose_name="Ціна квитка"
    )  # 💰

    def __str__(self):
        return f"{self.movie.title} – {self.datetime.strftime('%Y-%m-%d %H:%M')}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            seats_to_create = [
                Seat(session=self, row=r, column=c)
                for r in range(1, self.hall.rows + 1)
                for c in range(1, self.hall.seats_per_row + 1)
            ]
            Seat.objects.bulk_create(seats_to_create)


class Viewer(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='viewer',
        null=True,
        blank=True
    )
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    age = models.PositiveIntegerField(blank=True, null=True)
    gender = models.CharField(
        max_length=10,
        choices=[("male", "Чоловічий"), ("female", "Жіночий")],
        blank=True,
        null=True
    )
    avatar = models.ImageField(
        upload_to="profile_images/",
        default="profile_images/standart_avatar.png"
    )
    is_online = models.BooleanField(default=False)  # 👈 хто зараз дивиться

    def __str__(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip()

    @property
    def sessions(self):
        return Session.objects.filter(seats__viewer=self).distinct()


class Seat(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="seats")
    row = models.PositiveIntegerField()
    column = models.PositiveIntegerField()
    is_reserved = models.BooleanField(default=False)
    viewer = models.ForeignKey(
        Viewer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seats"
    )

    class Meta:
        unique_together = ("session", "row", "column")

    def __str__(self):
        return f"Row {self.row}, Col {self.column} – {'Reserved' if self.is_reserved else 'Free'}"


class Bookmark(models.Model):
    STATUS_CHOICES = [
        ('nothing', '-----'),
        ('planned', '🎬 У планах'),
        ('watching', '👀 Дивлюся'),
        ('completed', '✅ Переглянуто'),
        ('favorite', '❤️ Улюблене'),
        ('dropped', '💤 Кинуто'),
        ('rewatch', '🔁 Переглянути ще раз'),
    ]

    viewer = models.ForeignKey(Viewer, on_delete=models.CASCADE, related_name='bookmarks')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='bookmarks')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('viewer', 'movie')

    def __str__(self):
        return f"{self.viewer} — {self.movie} ({self.get_status_display()})"


class Rating(models.Model):
    viewer = models.ForeignKey(Viewer, on_delete=models.CASCADE, related_name='ratings')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='ratings')
    score = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('viewer', 'movie')

    def __str__(self):
        return f"{self.viewer} — {self.movie}: {self.score}"


class Friendship(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Запрошено'),
        ('accepted', 'Прийнято'),
        ('rejected', 'Відхилено'),
    ]
    from_viewer = models.ForeignKey(
        Viewer, on_delete=models.CASCADE, related_name='friendship_from'
    )
    to_viewer = models.ForeignKey(
        Viewer, on_delete=models.CASCADE, related_name='friendship_to'
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('from_viewer', 'to_viewer')

    def clean(self):
        if self.from_viewer_id == self.to_viewer_id:
            raise ValidationError('Не можна додати в друзі самого себе.')

        exists_reverse = Friendship.objects.filter(
            from_viewer=self.to_viewer,
            to_viewer=self.from_viewer
        ).exclude(pk=self.pk).exists()
        if exists_reverse:
            raise ValidationError('Запит дружби вже існує у зворотному напрямку.')

    def __str__(self):
        return f"{self.from_viewer} → {self.to_viewer} ({self.status})"


def are_friends(a: Viewer, b: Viewer) -> bool:
    return Friendship.objects.filter(
        models.Q(from_viewer=a, to_viewer=b, status='accepted') |
        models.Q(from_viewer=b, to_viewer=a, status='accepted')
    ).exists()


def friendship_status(a: Viewer, b: Viewer) -> str:
    """Повертає один із: 'self' | 'friends' | 'outgoing' | 'incoming' | 'none' | 'blocked' (якщо захочеш розширювати)."""
    if a.id == b.id:
        return 'self'
    pair = Friendship.objects.filter(
        models.Q(from_viewer=a, to_viewer=b) | models.Q(from_viewer=b, to_viewer=a)
    ).order_by('-created_at').first()
    if not pair:
        return 'none'
    if pair.status == 'accepted':
        return 'friends'
    if pair.from_viewer_id == a.id and pair.status == 'pending':
        return 'outgoing'
    if pair.to_viewer_id == a.id and pair.status == 'pending':
        return 'incoming'
    return 'none'


class Message(models.Model):
    sender = models.ForeignKey(Viewer, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(Viewer, on_delete=models.CASCADE, related_name='received_messages')
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)  # 👈 нове поле

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sender} → {self.receiver}: {self.text[:30]}"


class OnlineSeat(models.Model):
    """Місця у віртуальному онлайн-залі, незалежні від звичайних сеансів."""
    viewer = models.ForeignKey(Viewer, on_delete=models.SET_NULL, null=True, blank=True)
    row = models.PositiveIntegerField()
    column = models.PositiveIntegerField()
    is_reserved = models.BooleanField(default=False)

    class Meta:
        unique_together = ('row', 'column')

    def __str__(self):
        return f"Online Seat {self.row}-{self.column}: {'busy' if self.is_reserved else 'free'}"


class GlobalChatMessage(models.Model):
    sender = models.ForeignKey(Viewer, on_delete=models.CASCADE, related_name='global_messages')
    receiver = models.ForeignKey(
        Viewer,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='private_messages'
    )
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_private = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sender} → {self.receiver or 'ALL'}: {self.text[:40]}"

class LiveWatchSession(models.Model):
    from .models import Movie  # если Movie в другом файле — поправь импорт выше

    movie = models.OneToOneField(
        'schedule.Movie',        # или просто Movie, если в этом же файле
        on_delete=models.CASCADE,
        related_name='live_session'
    )
    started_at = models.DateTimeField(default=timezone.now)

    def get_position_seconds(self):
        delta = timezone.now() - self.started_at
        pos = delta.total_seconds()
        if pos < 0:
            pos = 0
        return pos

    def __str__(self):
        return f"Live session for {self.movie.title}"

class MovieActivity(models.Model):
    viewer = models.ForeignKey(Viewer, on_delete=models.CASCADE, related_name='activities')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='activities')
    time_spent = models.FloatField(default=0.0)  # в секундах
    watched_trailer = models.BooleanField(default=False)
    watched_movie = models.BooleanField(default=False)
    last_visit = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('viewer', 'movie')

    def __str__(self):
        return f"{self.viewer} — {self.movie} ({self.time_spent:.1f}s)"


# 💰 Кошелек глядача
class Wallet(models.Model):
    viewer = models.OneToOneField(Viewer, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet {self.viewer} — {self.balance}₴"


# 🎁 Промокоди
class PromoCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    max_uses = models.PositiveIntegerField(default=1, verbose_name="Макс. використань")
    used_count = models.PositiveIntegerField(default=0, verbose_name="Вже використано")
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    used_by = models.ManyToManyField(Viewer, related_name='used_promocodes', blank=True)

    def __str__(self):
        return f"{self.code} (+{self.amount}₴)"

    def is_valid_for(self, viewer):
        """Перевірка, чи можна використати промокод цим користувачем"""
        if not self.is_active:
            return False, "Промокод неактивний."
        if self.expires_at and timezone.now() > self.expires_at:
            return False, "Строк дії промокоду вичерпано."
        if self.used_by.filter(id=viewer.id).exists():
            return False, "Ви вже використали цей промокод."
        if self.used_count >= self.max_uses:
            return False, "Ліміт активацій промокоду вичерпано."
        return True, None

    def mark_used(self, viewer):
        """Позначаємо використання промокоду"""
        self.used_by.add(viewer)
        self.used_count += 1
        self.save(update_fields=["used_count"])


# 💳 Історія транзакцій
class Transaction(models.Model):
    TYPES = [
        ('deposit', 'Поповнення'),
        ('spend', 'Списання'),
        ('promo', 'Промокод'),
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=10, choices=TYPES)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.wallet.viewer} | {self.get_type_display()} {self.amount}₴"
