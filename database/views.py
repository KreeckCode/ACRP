from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from .models import Database, Entry
from .forms import DatabaseForm, EntryForm


class DatabaseListView(ListView):
    model = Database
    template_name = "database/database_list.html"
    context_object_name = "databases"


class DatabaseCreateView(CreateView):
    model = Database
    form_class = DatabaseForm
    template_name = "database/database_form.html"
    success_url = reverse_lazy("database:database_list")


class DatabaseDetailView(DetailView):
    model = Database
    template_name = "database/database_detail.html"
    context_object_name = "database"


class DatabaseUpdateView(UpdateView):
    model = Database
    form_class = DatabaseForm
    template_name = "database/database_form.html"
    success_url = reverse_lazy("database:database_list")


class DatabaseDeleteView(DeleteView):
    model = Database
    template_name = "database/database_confirm_delete.html"
    success_url = reverse_lazy("database:database_list")


class EntryListView(ListView):
    model = Entry
    template_name = "database/entry_list.html"
    context_object_name = "entries"

    def get_queryset(self):
        database_id = self.kwargs.get("database_id")
        return Entry.objects.filter(database_id=database_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        database_id = self.kwargs.get("database_id")
        # Add the database object to the context so the template can access its id and name.
        context["database"] = get_object_or_404(Database, id=database_id)
        return context


class EntryCreateView(CreateView):
    model = Entry
    form_class = EntryForm
    template_name = "database/entry_form.html"

    def get_initial(self):
        database_id = self.kwargs.get("database_id")
        database = get_object_or_404(Database, id=database_id)
        # Pre-populate the database field with the selected database.
        return {"database": database}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        database_id = self.kwargs.get("database_id")
        context["database"] = get_object_or_404(Database, id=database_id)
        return context

    def form_valid(self, form):
        database_id = self.kwargs.get("database_id")
        database = get_object_or_404(Database, id=database_id)
        # Explicitly set the database field on the entry instance.
        form.instance.database = database
        return super().form_valid(form)

    def get_success_url(self):
        database_id = self.kwargs.get("database_id")
        return reverse_lazy("database:entry_list", kwargs={"database_id": database_id})
