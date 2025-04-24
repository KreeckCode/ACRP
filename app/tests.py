from django.test import TestCase
from django.urls import reverse
from .models import Event, Announcement, Project, Task, Resource

class EventTestCase(TestCase):
    def setUp(self):
        Event.objects.create(title="Sample Event", start_time="2023-12-10 10:00:00", end_time="2023-12-10 12:00:00")

    def test_event_creation(self):
        event = Event.objects.get(title="Sample Event")
        self.assertEqual(event.title, "Sample Event")

    def test_event_list_view(self):
        response = self.client.get(reverse('event_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sample Event")

class AnnouncementTestCase(TestCase):
    def setUp(self):
        Announcement.objects.create(title="Sample Announcement", content="This is a test announcement.")

    def test_announcement_creation(self):
        announcement = Announcement.objects.get(title="Sample Announcement")
        self.assertEqual(announcement.title, "Sample Announcement")

    def test_announcement_list_view(self):
        response = self.client.get(reverse('announcement_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sample Announcement")

class ProjectTestCase(TestCase):
    def setUp(self):
        Project.objects.create(name="Sample Project", start_date="2023-12-01", end_date="2024-01-01", status="IN_PROGRESS")

    def test_project_creation(self):
        project = Project.objects.get(name="Sample Project")
        self.assertEqual(project.name, "Sample Project")

    def test_project_list_view(self):
        response = self.client.get(reverse('project_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sample Project")
