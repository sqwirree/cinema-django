from django.contrib import admin
from .models import (
    Genre, Movie, Hall, Session, Viewer, Seat,
    PromoCode, Wallet, Transaction
)

# ===== 🎬 Фильмы и Жанры =====

@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'get_genres', 'release_year', 'image')
    search_fields = ["title"]
    list_filter = ("genres", "release_year")

    def get_genres(self, obj):
        """Показывает все жанры фильма через запятую в списке фильмов"""
        return ", ".join([g.name for g in obj.genres.all()])
    get_genres.short_description = "Жанры"


# ===== 🎟️ Залы и Сеансы =====

@admin.register(Hall)
class HallAdmin(admin.ModelAdmin):
    list_display = ("name", "rows", "seats_per_row")


class SeatInline(admin.TabularInline):
    model = Seat
    extra = 0
    fields = ("row", "column", "is_reserved", "viewer")
    ordering = ("row", "column")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("movie", "hall", "datetime")
    list_filter = ("hall", "movie", "datetime")
    search_fields = ("movie__title",)
    inlines = [SeatInline]


# ===== 👤 Зрители =====

@admin.register(Viewer)
class ViewerAdmin(admin.ModelAdmin):
    list_display = ("get_full_name", "email", "age", "gender", "user")
    search_fields = ["first_name", "last_name", "email"]
    list_filter = ("gender",)

    def get_full_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}"
        return f"{obj.first_name or ''} {obj.last_name or ''}".strip()
    get_full_name.short_description = "Имя и Фамилия"


# ===== 💺 Места =====

@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("session", "row", "column", "is_reserved", "viewer")
    list_filter = ("session", "is_reserved")
    search_fields = ("viewer__first_name", "viewer__email")


# ===== 💰 Кошелёк =====

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("viewer", "balance", "updated_at")
    search_fields = ("viewer__first_name", "viewer__email")
    ordering = ("-updated_at",)


# ===== 📜 Транзакции =====

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "type", "amount", "description", "created_at")
    list_filter = ("type",)
    search_fields = ("wallet__viewer__first_name", "description")
    ordering = ("-created_at",)


# ===== 🎁 Промокоды =====

@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "amount", "is_active", "expires_at", "used_count", "max_uses")
    list_filter = ("is_active",)
    search_fields = ("code",)
    readonly_fields = ("used_by_display",)

    def used_by_display(self, obj):
        users = [v.first_name or v.email for v in obj.used_by.all()]
        return ", ".join(users) if users else "—"
    used_by_display.short_description = "Использовали"

    fieldsets = (
        (None, {
            "fields": ("code", "amount", "max_uses", "is_active", "expires_at")
        }),
        ("Использование", {
            "fields": ("used_count", "used_by_display"),
        }),
    )
