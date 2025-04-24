from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import ChatRoom, Message
from .forms import ChatRoomForm, MessageForm

@login_required
def chat_room_list(request):
    # List only the chat rooms the current user participates in.
    rooms = request.user.chat_rooms.all()
    return render(request, 'chat/chat_room_list.html', {'rooms': rooms})

@login_required
def chat_room_detail(request, room_id):
    room = get_object_or_404(ChatRoom, id=room_id)
    # Ensure the current user is a participant.
    if request.user not in room.participants.all():
        room.participants.add(request.user)
    msgs = room.messages.all()
    if request.method == 'POST':
        form = MessageForm(request.POST, request.FILES)
        if form.is_valid():
            message = form.save(commit=False)
            message.room = room
            message.sender = request.user
            message.save()
            messages.success(request, "Message sent.")
            return redirect('chat:chat_room_detail', room_id=room.id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = MessageForm()
    return render(request, 'chat/chat_room_detail.html', {
        'room': room,
        'messages': msgs,
        'form': form
    })

@login_required
def chat_room_create(request):
    initial_data = {}
    student_email = request.GET.get('student_email')
    if student_email:
        # Pre-populate the chat room name with the student's email
        initial_data['name'] = f"Document Request - {student_email}"
    if request.method == 'POST':
        form = ChatRoomForm(request.POST)
        if form.is_valid():
            room = form.save()
            # Ensure the creator is included as a participant.
            room.participants.add(request.user)
            messages.success(request, "Chat room created successfully.")
            return redirect('chat:chat_room_detail', room_id=room.id)
        else:
            messages.error(request, "There were errors in your submission.")
    else:
        form = ChatRoomForm(initial=initial_data)
    return render(request, 'chat/chat_room_create.html', {'form': form})


@login_required
def chat_room_delete(request, room_id):
    room = get_object_or_404(ChatRoom, id=room_id)
    if request.method == 'POST':
        room.delete()
        messages.success(request, "Chat room deleted successfully.")
        return redirect('chat:chat_room_list')
    return render(request, 'chat/chat_room_confirm_delete.html', {'room': room})
