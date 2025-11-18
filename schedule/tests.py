from django.test import TestCase
from django.urls import reverse
from .models import Movie, Genre

class MovieListViewTests(TestCase):
    def test_movie_list_view(self):
        genre = Genre.objects.create(name="Action")
        Movie.objects.create(title="Test Movie", genre=genre, release_year=2025)
        response = self.client.get(reverse('movie_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Movie")