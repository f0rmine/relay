export const messages = {
  en: {
    common: {
      back: 'Back',
      cancel: 'Cancel',
      email: 'Email',
      displayName: 'Display name',
      username: 'Username',
      password: 'Password',
      user: 'User',
      unknownUser: 'Unknown user',
      chat: 'Chat',
      me: 'Me',
      you: 'You',
      loading: 'Loading'
    },
    language: {
      label: 'Language',
      english: 'English',
      ukrainian: 'Ukrainian'
    },
    auth: {
      login: {
        subtitle: 'Sign in to continue.',
        loginLabel: 'Username or email',
        action: 'Log in',
        createAccount: 'Create account',
        failed: 'Login failed'
      },
      register: {
        title: 'Create account',
        subtitle: 'Use an email you can recover later.',
        action: 'Create account',
        existingAccount: 'I already have an account',
        failed: 'Registration failed'
      }
    },
    conversations: {
      title: 'Chats',
      search: 'Search users',
      profile: 'Profile',
      emptyTitle: 'No conversations',
      emptyText: 'Search for a user to start chatting.',
      noMessages: 'No messages yet',
      ownPreview: 'You: {message}',
      loadFailed: 'Could not load conversations'
    },
    search: {
      title: 'Search users',
      placeholder: 'Username, display name, email',
      emptyTitle: 'Find people',
      emptyText: 'Registered users appear here.',
      failed: 'Search failed',
      startFailed: 'Could not start chat'
    },
    profile: {
      title: 'Profile',
      changeAvatar: 'Change avatar',
      save: 'Save',
      logout: 'Log out',
      updateFailed: 'Profile update failed',
      avatarTypeFailed: 'Avatar upload failed: choose a JPG, PNG, WebP, or GIF image.',
      avatarUploadFailed: 'Avatar upload failed: {error}',
      unknownError: 'unknown error'
    },
    chat: {
      loadOlder: 'Load older',
      opening: 'Opening...',
      imageUnavailable: 'Image unavailable',
      deletedBy: '{name} deleted message',
      sending: 'sending',
      actionTitle: 'Message',
      deleteEveryone: 'Delete for everyone',
      attachFile: 'Attach file',
      messagePlaceholder: 'Message',
      sendMessage: 'Send message',
      removeAttachment: 'Remove',
      typing: 'typing...',
      loadFailed: 'Chat loading failed',
      sendFailed: 'Message send failed',
      deleteFailed: 'Message delete failed',
      realtimeUnavailable: 'Realtime connection is not ready. Wait a moment and try again.'
    },
    message: {
      deleted: 'Message deleted',
      image: 'Image',
      attachment: 'Attachment',
      generic: 'Message'
    },
    presence: {
      online: 'online',
      offline: 'offline',
      lastSeen: 'last seen {date}'
    },
    notifications: {
      channelName: 'Messages',
      channelDescription: 'New chat message notifications',
      newMessage: 'New message'
    },
    api: {
      requestFailed: 'Request failed',
      cannotReach: 'Cannot reach backend at {url}. Check the server, Tailscale/LAN IP, and mobile .env URL.',
      errors: {
        missingAuth: 'Authentication is required',
        userNotFound: 'User not found',
        tokenExpired: 'Your session has expired',
        invalidToken: 'Your session is invalid. Please log in again.',
        invalidCredentials: 'Invalid username, email, or password',
        invalidResetToken: 'The password reset link is invalid or expired',
        tooManyAttempts: 'Too many attempts. Try again later.',
        usernameExists: 'This username is already in use',
        emailExists: 'This email is already in use',
        displayNameRequired: 'Display name is required',
        conversationNotFound: 'Conversation not found',
        selfConversation: 'You cannot start a conversation with yourself',
        emptyMessage: 'Enter a message or attach a file',
        invalidAttachment: 'The selected attachment is invalid',
        messageNotFound: 'Message not found',
        deleteForbidden: 'Only the sender can delete this message',
        unsupportedFileType: 'This file type is not supported',
        fileTypeMismatch: 'The file extension does not match its type',
        emptyFile: 'The selected file is empty',
        fileTooLarge: 'The selected file is too large',
        imageTypeMismatch: 'The image content does not match its file type',
        fileMissing: 'The file is missing from storage',
        attachmentNotFound: 'Attachment not found',
        emptyAvatar: 'The selected avatar file is empty',
        unsupportedAvatarType: 'This avatar image type is not supported',
        avatarTypeMismatch: 'The avatar extension does not match its type',
        avatarContentMismatch: 'The avatar content does not match its file type',
        avatarTooLarge: 'The avatar image is too large'
      }
    },
    app: {
      pressAgainToExit: 'Press again to exit'
    }
  },
  uk: {
    common: {
      back: 'Назад',
      cancel: 'Скасувати',
      email: 'Електронна пошта',
      displayName: 'Ім’я для відображення',
      username: 'Ім’я користувача',
      password: 'Пароль',
      user: 'Користувач',
      unknownUser: 'Невідомий користувач',
      chat: 'Чат',
      me: 'Я',
      you: 'Ви',
      loading: 'Завантаження'
    },
    language: {
      label: 'Мова',
      english: 'Англійська',
      ukrainian: 'Українська'
    },
    auth: {
      login: {
        subtitle: 'Увійдіть, щоб продовжити.',
        loginLabel: 'Ім’я користувача або електронна пошта',
        action: 'Увійти',
        createAccount: 'Створити обліковий запис',
        failed: 'Не вдалося увійти'
      },
      register: {
        title: 'Створити обліковий запис',
        subtitle: 'Використайте адресу, до якої зможете відновити доступ.',
        action: 'Створити обліковий запис',
        existingAccount: 'У мене вже є обліковий запис',
        failed: 'Не вдалося зареєструватися'
      }
    },
    conversations: {
      title: 'Чати',
      search: 'Пошук користувачів',
      profile: 'Профіль',
      emptyTitle: 'Немає чатів',
      emptyText: 'Знайдіть користувача, щоб розпочати спілкування.',
      noMessages: 'Повідомлень ще немає',
      ownPreview: 'Ви: {message}',
      loadFailed: 'Не вдалося завантажити чати'
    },
    search: {
      title: 'Пошук користувачів',
      placeholder: 'Ім’я користувача, ім’я для відображення або електронна пошта',
      emptyTitle: 'Знайдіть людей',
      emptyText: 'Тут з’являтимуться зареєстровані користувачі.',
      failed: 'Пошук не вдався',
      startFailed: 'Не вдалося розпочати чат'
    },
    profile: {
      title: 'Профіль',
      changeAvatar: 'Змінити аватар',
      save: 'Зберегти',
      logout: 'Вийти',
      updateFailed: 'Не вдалося оновити профіль',
      avatarTypeFailed: 'Не вдалося завантажити аватар: виберіть зображення JPG, PNG, WebP або GIF.',
      avatarUploadFailed: 'Не вдалося завантажити аватар: {error}',
      unknownError: 'невідома помилка'
    },
    chat: {
      loadOlder: 'Завантажити попередні',
      opening: 'Відкривання...',
      imageUnavailable: 'Зображення недоступне',
      deletedBy: '{name} видалив(-ла) повідомлення',
      sending: 'надсилання',
      actionTitle: 'Повідомлення',
      deleteEveryone: 'Видалити для всіх',
      attachFile: 'Прикріпити файл',
      messagePlaceholder: 'Повідомлення',
      sendMessage: 'Надіслати повідомлення',
      removeAttachment: 'Видалити',
      typing: 'друкує...',
      loadFailed: 'Не вдалося завантажити чат',
      sendFailed: 'Не вдалося надіслати повідомлення',
      deleteFailed: 'Не вдалося видалити повідомлення',
      realtimeUnavailable: 'З’єднання в реальному часі ще не готове. Зачекайте трохи та спробуйте ще раз.'
    },
    message: {
      deleted: 'Повідомлення видалено',
      image: 'Зображення',
      attachment: 'Вкладення',
      generic: 'Повідомлення'
    },
    presence: {
      online: 'в мережі',
      offline: 'не в мережі',
      lastSeen: 'був(-ла) в мережі {date}'
    },
    notifications: {
      channelName: 'Повідомлення',
      channelDescription: 'Сповіщення про нові повідомлення в чаті',
      newMessage: 'Нове повідомлення'
    },
    api: {
      requestFailed: 'Запит не вдався',
      cannotReach: 'Не вдається підключитися до сервера {url}. Перевірте сервер, IP-адресу Tailscale/LAN та URL-адресу в mobile .env.',
      errors: {
        missingAuth: 'Потрібна автентифікація',
        userNotFound: 'Користувача не знайдено',
        tokenExpired: 'Термін дії сеансу завершився',
        invalidToken: 'Сеанс недійсний. Увійдіть знову.',
        invalidCredentials: 'Неправильне ім’я користувача, електронна пошта або пароль',
        invalidResetToken: 'Посилання для скидання пароля недійсне або застаріло',
        tooManyAttempts: 'Забагато спроб. Повторіть пізніше.',
        usernameExists: 'Це ім’я користувача вже використовується',
        emailExists: 'Ця електронна пошта вже використовується',
        displayNameRequired: 'Вкажіть ім’я для відображення',
        conversationNotFound: 'Чат не знайдено',
        selfConversation: 'Не можна розпочати чат із собою',
        emptyMessage: 'Введіть повідомлення або прикріпіть файл',
        invalidAttachment: 'Вибране вкладення недійсне',
        messageNotFound: 'Повідомлення не знайдено',
        deleteForbidden: 'Лише відправник може видалити це повідомлення',
        unsupportedFileType: 'Цей тип файлу не підтримується',
        fileTypeMismatch: 'Розширення файлу не відповідає його типу',
        emptyFile: 'Вибраний файл порожній',
        fileTooLarge: 'Вибраний файл завеликий',
        imageTypeMismatch: 'Вміст зображення не відповідає типу файлу',
        fileMissing: 'Файл відсутній у сховищі',
        attachmentNotFound: 'Вкладення не знайдено',
        emptyAvatar: 'Вибраний файл аватара порожній',
        unsupportedAvatarType: 'Цей тип зображення аватара не підтримується',
        avatarTypeMismatch: 'Розширення аватара не відповідає його типу',
        avatarContentMismatch: 'Вміст аватара не відповідає типу файлу',
        avatarTooLarge: 'Зображення аватара завелике'
      }
    },
    app: {
      pressAgainToExit: 'Натисніть ще раз, щоб вийти'
    }
  }
} as const;
