(function () {
  const catalogs = {
    es: {
      'Home': 'Inicio',
      'Student': 'Estudiante',
      'Instructor': 'Instructor',
      'Analytics': 'Analíticas',
      'Profile': 'Perfil',
      'Login': 'Iniciar sesión',
      'Sign Up': 'Registrarse',
      'Info': 'Información',
      'Account': 'Cuenta',
      'Logout': 'Cerrar sesión',
      'Exit': 'Salir',
      'Language': 'Idioma',
      'Breadcrumb': 'Ruta de navegación',
      'User menu': 'Menú de usuario',
      'Account menu': 'Menú de cuenta',
      'Toggle theme': 'Cambiar tema',
      'Switch to dark mode': 'Cambiar a modo oscuro',
      'Switch to light mode': 'Cambiar a modo claro',
      'Open navigation': 'Abrir navegación',
      'Close navigation': 'Cerrar navegación',

      'Run modules, launches, enrollment, and progress from one workspace.': 'Ejecuta módulos, accesos, inscripciones y progreso desde un solo espacio de trabajo.',
      'Open Instructor Dashboard': 'Abrir panel del instructor',
      'Open Student Dashboard': 'Abrir panel del estudiante',
      'Sign In': 'Iniciar sesión',
      'Create Account': 'Crear cuenta',
      'Students': 'Estudiantes',
      'Launch modules': 'Abrir módulos',
      'Pick up assignments, open tools, and review course progress.': 'Continúa tareas, abre herramientas y revisa el progreso del curso.',
      'Instructors': 'Instructores',
      'Manage sessions': 'Gestionar sesiones',
      'Create course sessions, enroll learners, and review analytics.': 'Crea sesiones, inscribe estudiantes y revisa analíticas.',
      'Role dashboards': 'Paneles por rol',
      'Focused views keep student and instructor work separate.': 'Las vistas enfocadas mantienen separado el trabajo de estudiantes e instructores.',
      'External tools': 'Herramientas externas',
      'LTI and embedded tools launch from course pages.': 'Las herramientas LTI e incrustadas se abren desde las páginas del curso.',
      'Progress data': 'Datos de progreso',
      'Completion, scores, and timelines stay attached to sessions.': 'La finalización, las puntuaciones y las cronologías quedan asociadas a las sesiones.',

      'Need an account?': '¿Necesitas una cuenta?',
      'Create one here': 'Créala aquí',
      'Already registered?': '¿Ya estás registrado?',
      'Sign in here': 'Inicia sesión aquí',
      'Password checks': 'Comprobaciones de contraseña',
      'At least 8 characters': 'Al menos 8 caracteres',
      'Not entirely numeric': 'No totalmente numérica',
      'Avoids your profile details': 'Evita los datos de tu perfil',
      'Passwords match': 'Las contraseñas coinciden',
      'Username': 'Nombre de usuario',
      'Email': 'Correo electrónico',
      'Full Name': 'Nombre completo',
      'Role': 'Rol',
      'Password': 'Contraseña',
      'Password confirmation': 'Confirmación de contraseña',
      'Current password': 'Contraseña actual',
      'New password': 'Nueva contraseña',
      'New password confirmation': 'Confirmación de nueva contraseña',
      'Your email address': 'Tu correo electrónico',
      'Your display name': 'Tu nombre visible',
      "We'll never share your email with anyone else.": 'Nunca compartiremos tu correo electrónico.',
      'An account with this email address already exists.': 'Ya existe una cuenta con este correo electrónico.',
      'Dismiss message': 'Cerrar mensaje',
      'Registration successful.': 'Registro completado correctamente.',
      'Successfully signed in.': 'Sesión iniciada correctamente.',
      'Successfully signed in to ModuLearn.': 'Sesión iniciada correctamente en ModuLearn.',
      'Invalid username or password.': 'Nombre de usuario o contraseña no válidos.',
      'Authentication service temporarily unavailable. Please try again later.': 'El servicio de autenticación no está disponible temporalmente. Inténtalo de nuevo más tarde.',
      'Profile updated successfully.': 'Perfil actualizado correctamente.',
      'Password changed successfully.': 'Contraseña cambiada correctamente.',
      'KnowledgeTree account provisioned successfully.': 'Cuenta de KnowledgeTree aprovisionada correctamente.',
      'Password reset successfully in both ModuLearn and KnowledgeTree.': 'Contraseña restablecida correctamente en ModuLearn y KnowledgeTree.',
      'Could not provision KnowledgeTree account:': 'No se pudo aprovisionar la cuenta de KnowledgeTree:',
      'Password updated in ModuLearn, but KnowledgeTree update failed:': 'La contraseña se actualizó en ModuLearn, pero falló la actualización en KnowledgeTree:',
      'Error resetting password:': 'Error al restablecer la contraseña:',

      'Profile Summary': 'Resumen del perfil',
      'No email on file': 'No hay correo electrónico registrado',
      'No role assigned': 'Sin rol asignado',
      'Integration Status': 'Estado de integraciones',
      'KnowledgeTree': 'KnowledgeTree',
      'Linked for legacy dashboards and resource access.': 'Vinculado para paneles heredados y acceso a recursos.',
      'Not linked yet. Provisioning remains available below when enabled.': 'Aún no vinculado. El aprovisionamiento aparece abajo cuando está habilitado.',
      'Connected': 'Conectado',
      'Not Linked': 'No vinculado',
      'LTI Launch Data': 'Datos de inicio LTI',
      'Stored launch payloads remain available for troubleshooting and support.': 'Los datos de inicio guardados quedan disponibles para soporte y resolución de problemas.',
      'Available': 'Disponible',
      'None': 'Ninguno',
      'Legacy Groups': 'Grupos heredados',
      'KnowledgeTree teaching groups': 'Grupos docentes de KnowledgeTree',
      'Search groups...': 'Buscar grupos...',
      'Open Legacy Dashboard': 'Abrir panel heredado',
      'View Resources': 'Ver recursos',
      'No groups match your search.': 'Ningún grupo coincide con tu búsqueda.',
      'Edit profile': 'Editar perfil',
      'Keep your display information current so course enrollments and integrations stay understandable.': 'Mantén actualizada tu información para que las inscripciones e integraciones sean claras.',
      'Update Profile': 'Actualizar perfil',
      'Set password': 'Establecer contraseña',
      'Change password': 'Cambiar contraseña',
      'Use a strong password so your ModuLearn account stays secure across course and dashboard access.': 'Usa una contraseña segura para proteger tu cuenta de ModuLearn.',
      'Password changes apply to ModuLearn only unless you are also using a linked KnowledgeTree account.': 'Los cambios de contraseña se aplican solo a ModuLearn salvo que uses una cuenta KnowledgeTree vinculada.',
      'Set Password': 'Establecer contraseña',
      'Change Password': 'Cambiar contraseña',
      'Provision KnowledgeTree access': 'Aprovisionar acceso a KnowledgeTree',
      'Create or link your legacy platform account so you can open existing KnowledgeTree and MasteryGrids experiences.': 'Crea o vincula tu cuenta heredada para abrir experiencias existentes de KnowledgeTree y MasteryGrids.',
      'Create KnowledgeTree Account': 'Crear cuenta KnowledgeTree',
      'Reset synchronized password': 'Restablecer contraseña sincronizada',
      'This updates both ModuLearn and KnowledgeTree so the linked account stays in sync.': 'Esto actualiza ModuLearn y KnowledgeTree para mantener sincronizada la cuenta vinculada.',
      'Reset Password': 'Restablecer contraseña',
      'Session': 'Sesión',
      'End the current browser session when you’re working on a shared or public machine.': 'Cierra la sesión actual si trabajas en una computadora compartida o pública.',
      'Log Out': 'Cerrar sesión',

      'Student Dashboard': 'Panel del estudiante',
      'Instructor Dashboard': 'Panel del instructor',
      'Course Dashboard': 'Panel del curso',
      'Course Sessions': 'Sesiones del curso',
      'Course Session': 'Sesión del curso',
      'Course Structures': 'Estructuras del curso',
      'Course Structure': 'Estructura del curso',
      'Courses': 'Cursos',
      'Studies': 'Estudios',
      'Study': 'Estudio',
      'Study Controls': 'Controles del estudio',
      'Session Controls': 'Controles de la sesión',
      'Configure': 'Configurar',
      'Configure Modules': 'Configurar módulos',
      'Preview': 'Vista previa',
      'Manage Courses': 'Gestionar cursos',
      'Manage Studies': 'Gestionar estudios',
      'Create New Study': 'Crear nuevo estudio',
      'New Study': 'Nuevo estudio',
      'Study Title': 'Título del estudio',
      'Required': 'Obligatorio',
      'Conditions': 'Condiciones',
      'Create Study': 'Crear estudio',
      'Create Demo Course': 'Crear curso de demostración',
      'Import Course': 'Importar curso',
      'Import Course Structure from JSON': 'Importar estructura del curso desde JSON',
      'Import JSON': 'Importar JSON',
      'Course imported successfully!': 'Curso importado correctamente.',
      'Manage Enrollment': 'Gestionar inscripción',
      'View Course': 'Ver curso',
      'View Dashboard': 'Ver panel',
      'View All': 'Ver todo',
      'Active Course Sessions': 'Sesiones activas del curso',
      'Manage your active course sessions': 'Gestiona tus sesiones activas',
      'No reusable course structures yet. Import JSON, use Course Authoring, or create a custom session.': 'Aún no hay estructuras reutilizables. Importa JSON, usa Course Authoring o crea una sesión personalizada.',
      'Only instructors can create demo courses.': 'Solo los instructores pueden crear cursos de demostración.',
      'The demo course could not be created. Please try again.': 'No se pudo crear el curso de demostración. Inténtalo de nuevo.',
      'Demo course created. You can review and configure it here.': 'Curso de demostración creado. Puedes revisarlo y configurarlo aquí.',
      'Course visibility and locking controls were updated.': 'Se actualizaron los controles de visibilidad y bloqueo del curso.',
      'Unit added to the course structure.': 'Unidad agregada a la estructura del curso.',
      'Module added to the course structure.': 'Módulo agregado a la estructura del curso.',
      'Course plugin settings were updated.': 'Se actualizó la configuración de plugins del curso.',
      'Adaptive branching rules were updated.': 'Se actualizaron las reglas de ramificación adaptativa.',
      'Unknown course configuration action.': 'Acción de configuración del curso desconocida.',
      'That module is locked.': 'Ese módulo está bloqueado.',
      'You are not enrolled in this course.': 'No estás inscrito en este curso.',
      'This form has already been submitted.': 'Este formulario ya fue enviado.',
      'Please answer every required question.': 'Responde todas las preguntas obligatorias.',
      'Your response was submitted.': 'Tu respuesta fue enviada.',
      'You are not enrolled in this course session.': 'No estás inscrito en esta sesión del curso.',
      'Both email and code are required.': 'Se requieren el correo electrónico y el código.',
      'Invalid enrollment code or email.': 'Código de inscripción o correo electrónico no válido.',
      'You are already enrolled in this course.': 'Ya estás inscrito en este curso.',
      'Successfully enrolled in the course!': 'Inscripción en el curso completada correctamente.',
      'An error occurred during enrollment. Please try again.': 'Ocurrió un error durante la inscripción. Inténtalo de nuevo.',
      'Enrollment code created successfully.': 'Código de inscripción creado correctamente.',
      'Progress not tracked for instructors': 'El progreso no se registra para instructores',

      'Study Access': 'Acceso al estudio',
      'Your study sessions': 'Tus sesiones de estudio',
      'Resume the assigned session below. Other ModuLearn pages are hidden for study participant accounts.': 'Reanuda abajo la sesión asignada. Otras páginas de ModuLearn están ocultas para participantes del estudio.',
      'Study session': 'Sesión de estudio',
      'Resume': 'Reanudar',
      'Finished': 'Finalizado',
      'No module available': 'No hay módulo disponible',
      'Finish Study': 'Finalizar estudio',
      'Progress': 'Progreso',
      'No study sessions found': 'No se encontraron sesiones de estudio',
      'Open the participant link provided by your study platform to begin.': 'Abre el enlace de participante proporcionado por tu plataforma de estudio para comenzar.',
      'Study link unavailable': 'Enlace de estudio no disponible',
      'This recruitment link cannot be used right now.': 'Este enlace de reclutamiento no puede usarse en este momento.',
      'Study complete': 'Estudio completado',
      'Your response has been recorded. You may close this tab.': 'Tu respuesta ha sido registrada. Puedes cerrar esta pestaña.',
      'Continue To Study': 'Continuar al estudio',
      'Study entry': 'Entrada al estudio',

      'Form / Survey': 'Formulario / Encuesta',
      'Completion': 'Finalización',
      'Complete': 'Completado',
      'Not submitted': 'No enviado',
      'Submitting this form marks the module complete and can unlock downstream content.': 'Enviar este formulario marca el módulo como completado y puede desbloquear contenido posterior.',
      'Response submitted': 'Respuesta enviada',
      'This form is complete. Your instructor has disabled resubmission.': 'Este formulario está completo. Tu instructor deshabilitó el reenvío.',
      'This form does not have any questions yet.': 'Este formulario aún no tiene preguntas.',
      'Instructor preview only. Student submissions are disabled from this view.': 'Solo vista previa del instructor. Los envíos de estudiantes están deshabilitados en esta vista.',
      'Next Module': 'Siguiente módulo',
      'Check Next Module': 'Buscar siguiente módulo',
      'Checking...': 'Buscando...',
      'No Unlocked Module': 'No hay módulo desbloqueado',
      'Try Again': 'Intentar de nuevo',
      'Open the next module': 'Abrir el siguiente módulo',
      'No visible unlocked module is available yet': 'Aún no hay un módulo visible y desbloqueado',
      'Could not check the next module. Try again.': 'No se pudo buscar el siguiente módulo. Inténtalo otra vez.',
      'Check for the next unlocked module': 'Buscar el siguiente módulo desbloqueado',
      'Back To Course': 'Volver al curso',
      'Open': 'Abrir',
      'To-Do': 'Por hacer',
      'Done': 'Hecho',
      'Locked': 'Bloqueado',
      'Visible': 'Visible',
      'Hidden': 'Oculto',
      'Unlocked': 'Desbloqueado',

      'Study Analytics': 'Analíticas del estudio',
      'Condition Overview': 'Resumen de condiciones',
      'Assignment and progress by condition': 'Asignación y progreso por condición',
      'Participants': 'Participantes',
      'Condition roster and drilldown': 'Lista por condición y desglose',
      'Expand a participant to inspect every module.': 'Expande un participante para revisar cada módulo.',
      'Export CSV': 'Exportar CSV',
      'Dashboard': 'Panel',
      'Average Progress': 'Progreso promedio',
      'Participant Cap': 'Límite de participantes',
      'Assignment': 'Asignación',
      'Balanced': 'Balanceada',
      'Hash': 'Hash',
      'Schedule': 'Programada',
      'Completion Code': 'Código de finalización',
      'Screen-Out Code': 'Código de exclusión',
      'Attention-Fail Code': 'Código de fallo de atención',
      'Active link': 'Enlace activo',
      'Save Prolific Settings': 'Guardar configuración de Prolific',
      'Prolific Settings': 'Configuración de Prolific',
      'Prolific Recruitment': 'Reclutamiento Prolific',
      'Prolific active': 'Prolific activo',
      'Prolific paused': 'Prolific pausado',
      'No Prolific link': 'Sin enlace de Prolific',
      'Completion code ready': 'Código de finalización listo',
      'Needs completion code': 'Falta código de finalización',
      'Entry URL': 'URL de entrada',
      'Completion URL': 'URL de finalización',
      'Copy Entry': 'Copiar entrada',
      'Copy Credit': 'Copiar crédito',
      'Export': 'Exportar',
      'Clear & Reset': 'Borrar y reiniciar',
      'Clear Participants & Progress': 'Borrar participantes y progreso',
      'No available module was found for this study session.': 'No se encontró ningún módulo disponible para esta sesión de estudio.',
      'No active recruitment participant session was found for this course.': 'No se encontró una sesión activa de participante de reclutamiento para este curso.',
      'No active participant session was found for this study.': 'No se encontró una sesión activa de participante para este estudio.',
      'No Prolific completion code is configured for this outcome.': 'No hay un código de finalización de Prolific configurado para este resultado.',
      'Your study response was recorded, but SONA credit needs manual review.': 'Tu respuesta del estudio fue registrada, pero el crédito de SONA necesita revisión manual.',
      'Prolific recruitment is available now. SONA setup is temporarily disabled.': 'El reclutamiento por Prolific está disponible ahora. La configuración de SONA está deshabilitada temporalmente.',
      'Study reset was not confirmed. Type RESET to clear participant data.': 'El reinicio del estudio no fue confirmado. Escribe RESET para borrar los datos de participantes.',
      'Prolific recruitment has moved to Studies. Create or open a Study from the Instructor Dashboard.': 'El reclutamiento de Prolific se trasladó a Estudios. Crea o abre un estudio desde el panel del instructor.',

      'Configure modules, sequence, visibility, lock rules, and manual additions.': 'Configura módulos, secuencia, visibilidad, reglas de bloqueo y agregados manuales.',
      'Configure study modules, sequence, visibility, lock rules, and participant flow.': 'Configura módulos del estudio, secuencia, visibilidad, reglas de bloqueo y flujo de participantes.',
      'Course authoring tools': 'Herramientas de autoría del curso',
      'Add Unit': 'Agregar unidad',
      'Add Module': 'Agregar módulo',
      'Unit Builder': 'Constructor de unidades',
      'Module Builder': 'Constructor de módulos',
      'Add Content': 'Agregar contenido',
      'Course Plugins': 'Plugins del curso',
      'Plugin settings apply to this whole course structure.': 'La configuración de plugins se aplica a toda esta estructura del curso.',
      'Save Plugin Settings': 'Guardar configuración de plugins',
      'Adaptive Branching': 'Ramificación adaptativa',
      'Correct and incorrect next-module paths': 'Rutas de siguiente módulo correctas e incorrectas',
      'Branch targets are locked for everyone until a learner earns an individual unlock from the selected source module.': 'Los destinos de ramificación quedan bloqueados hasta que cada estudiante consiga un desbloqueo individual desde el módulo fuente seleccionado.',
      'Plugin enabled': 'Plugin activado',
      'Plugin disabled': 'Plugin desactivado',
      'Add Branch Rule': 'Agregar regla de ramificación',
      'From Module': 'Desde módulo',
      'Condition': 'Condición',
      'Unlock Module': 'Desbloquear módulo',
      'Score': 'Puntuación',
      'Any condition': 'Cualquier condición',
      'Choose source': 'Elegir fuente',
      'Choose condition': 'Elegir condición',
      'Choose target': 'Elegir destino',
      'Active': 'Activo',
      'Delete': 'Eliminar',
      'Save Branching Rules': 'Guardar reglas de ramificación',
      'No branching rules have been created yet.': 'Aún no se han creado reglas de ramificación.',
      'Correct / Successful': 'Correcto / Exitoso',
      'Incorrect / Unsuccessful': 'Incorrecto / No exitoso',
      'Completed': 'Completado',
      'Score At Least': 'Puntuación al menos',
      'Score Below': 'Puntuación menor que',
      'No unlock condition': 'Sin condición de desbloqueo',
      'Submit Button': 'Botón de envío',
      'Submit': 'Enviar',
      'Back': 'Atrás',
      'Cancel': 'Cancelar',
      'Save': 'Guardar',
      'Save Changes': 'Guardar cambios',

      'Learning Analytics Dashboard': 'Panel de analíticas de aprendizaje',
      'ModuLearn Analytics Dashboard': 'Panel de analíticas de ModuLearn',
      'ModuLearn Analytics': 'Analíticas de ModuLearn',
      'Track student progress across your ModuLearn course sessions': 'Da seguimiento al progreso estudiantil en tus sesiones de curso de ModuLearn',
      'Review progress, engagement, and struggling learners across your course sessions.': 'Revisa progreso, participación y estudiantes con dificultades en tus sesiones de curso.',
      'Legacy Analytics': 'Analíticas heredadas',
      'Launch Analytics': 'Iniciar analíticas',
      'Load Analytics': 'Cargar analíticas',
      'Loading...': 'Cargando...',
      '(Select a ModuLearn course session)': '(Selecciona una sesión de curso de ModuLearn)',
      '-- Select a course session --': '-- Selecciona una sesión de curso --',
      'Class Average': 'Promedio de la clase',
      'Per Student': 'Por estudiante',
      'Course Analytics': 'Analíticas del curso',
      'Course signal': 'Señal del curso',
      'Resource Profile': 'Perfil de recursos',
      'Group ID': 'ID del grupo',
      'Course ID': 'ID del curso',
      'Discovering Course IDs...': 'Buscando IDs de curso...',
      'Could not discover Course IDs. Please enter manually.': 'No se pudieron encontrar IDs de curso. Ingrésalos manualmente.',
      'No Course IDs found. Please enter manually.': 'No se encontraron IDs de curso. Ingrésalos manualmente.',
      'Invalid Group ID or Course ID': 'ID de grupo o curso no válido',
      'Group/Course combination not found': 'No se encontró la combinación grupo/curso',

      'Home - ModuLearn': 'Inicio - ModuLearn',
      'Info - ModuLearn': 'Información - ModuLearn',
      'Login - ModuLearn': 'Iniciar sesión - ModuLearn',
      'Sign Up - ModuLearn': 'Registrarse - ModuLearn',
      'Study Sessions - ModuLearn': 'Sesiones de estudio - ModuLearn',
      'Study Entry - ModuLearn': 'Entrada al estudio - ModuLearn',
      'Study Complete - ModuLearn': 'Estudio completado - ModuLearn',
      'Study Link Unavailable - ModuLearn': 'Enlace de estudio no disponible - ModuLearn',
      'Already Completed - ModuLearn': 'Ya completado - ModuLearn',
      'ModuLearn Content': 'Contenido de ModuLearn',
      'Active project': 'Proyecto activo',
      'What ModuLearn does, how it is built, and how to reach the maintainer.': 'Qué hace ModuLearn, cómo está construido y cómo contactar a la persona responsable.',
      'ModuLearn overview': 'Resumen de ModuLearn',
      'What it does': 'Qué hace',
      'Connects course pages, module launches, enrollment, analytics, and progress.': 'Conecta páginas de curso, aperturas de módulos, inscripción, analíticas y progreso.',
      'Integrations': 'Integraciones',
      'Supports LTI, embedded resources, and legacy KnowledgeTree workflows.': 'Admite LTI, recursos incrustados y flujos heredados de KnowledgeTree.',
      'Core stack': 'Base técnica',
      'Runtime': 'Entorno',
      'Framework': 'Framework',
      'Frontend': 'Frontend',
      'Local data': 'Datos locales',
      'Role paths': 'Rutas por rol',
      'Features': 'Funciones',
      'Contact': 'Contacto',
      'Problems or feedback?': '¿Problemas o comentarios?',
      'Email the maintainer!': '¡Envía un correo a la persona responsable!',
      'Include in your message': 'Incluye en tu mensaje',
      'Student or instructor': 'Estudiante o instructor',
      'Page': 'Página',
      'Route or screen': 'Ruta o pantalla',
      'Area': 'Área',
      'LTI, analytics, enrollment, course page': 'LTI, analíticas, inscripción, página del curso',
      'Evidence': 'Evidencia',
      'Screenshot or exact error': 'Captura de pantalla o error exacto',
      'Already completed': 'Ya completado',
      'This participant session has already been marked complete.': 'Esta sesión de participante ya fue marcada como completada.',
      'Your participant session is ready. Continue when you are ready to begin the study materials.': 'Tu sesión de participante está lista. Continúa cuando estés listo para iniciar los materiales del estudio.',
      'Platform': 'Plataforma',
      'Status': 'Estado',
      'Study Sessions': 'Sesiones de estudio',
      'Study Complete': 'Estudio completado',
      'This tool cannot be embedded here': 'Esta herramienta no se puede incrustar aquí',
      'The external tool has security restrictions that prevent iframe embedding.': 'La herramienta externa tiene restricciones de seguridad que impiden incrustarla en un iframe.',
      'Open In A New Window': 'Abrir en una nueva ventana',
      'Progress passback may be limited when the tool opens outside the embedded frame.': 'El envío de progreso puede ser limitado cuando la herramienta se abre fuera del marco incrustado.',
      "Your browser doesn't support iframes.": 'Tu navegador no admite iframes.',
      'Participant-facing copy and questions': 'Texto y preguntas para participantes',
      'Instructions': 'Instrucciones',
      'Allow resubmission': 'Permitir reenvío',
      'Question': 'Pregunta',
      'Add Question': 'Agregar pregunta',
      'Add questions': 'Agregar preguntas',
      'Optional helper text': 'Texto de ayuda opcional',
      'Multiple Choice - One Answer': 'Opción múltiple - una respuesta',
      'Multiple Choice - Multiple Answers': 'Opción múltiple - varias respuestas',
      'Short Answer': 'Respuesta corta',
      'Long Answer': 'Respuesta larga',
      'Likert Scale': 'Escala Likert',
      'Strongly disagree': 'Totalmente en desacuerdo',
      'Strongly agree': 'Totalmente de acuerdo',
      'Delete question': 'Eliminar pregunta',
      'Prompt': 'Enunciado',
      'Type': 'Tipo',
      'Order': 'Orden',
      'Options': 'Opciones',
      'I Consent': 'Doy mi consentimiento',
      'English': 'Inglés',
      'Spanish': 'Español'
    }
  };

  const prefixCatalogs = {
    es: {
      'Assigned condition:': 'Condición asignada:',
      'You have been enrolled in': 'Te has inscrito en',
      'You have unenrolled from': 'Te has dado de baja de',
      'Successfully removed': 'Se eliminó correctamente a',
      'Created study': 'Estudio creado',
      'The study could not be created:': 'No se pudo crear el estudio:',
      'Created Prolific recruitment for': 'Reclutamiento de Prolific creado para',
      'Updated Prolific recruitment for': 'Reclutamiento de Prolific actualizado para',
      'Could not provision KnowledgeTree account:': 'No se pudo aprovisionar la cuenta de KnowledgeTree:',
      'Password updated in ModuLearn, but KnowledgeTree update failed:': 'La contraseña se actualizó en ModuLearn, pero falló la actualización en KnowledgeTree:',
      'Error resetting password:': 'Error al restablecer la contraseña:',
      'Next up:': 'Siguiente:',
      'Completion code:': 'Código de finalización:',
      'Group ID:': 'ID del grupo:',
      'Course IDs:': 'IDs de curso:',
      'Login:': 'Usuario:',
      'User ID:': 'ID de usuario:',
      'Entered': 'Entró',
      'Last activity': 'Última actividad'
    }
  };

  const fragmentCatalogs = {
    es: {
      'Its Prolific study URL is ready to copy from Manage Studies.': 'La URL de estudio de Prolific está lista para copiarse desde Gestionar estudios.',
      'from the course': 'del curso',
      'Please contact support.': 'Contacta al soporte.'
    }
  };

  const language = (window.ModuLearnLanguage || document.documentElement.lang || 'en').toLowerCase().split('-')[0];
  const catalog = catalogs[language] || {};
  const prefixCatalog = prefixCatalogs[language] || {};
  const fragmentCatalog = fragmentCatalogs[language] || {};
  const attributes = [
    'aria-label',
    'title',
    'placeholder',
    'data-ready-label',
    'data-checking-label',
    'data-empty-label',
    'data-error-label'
  ];
  const skipSelector = 'script, style, code, pre, textarea, [data-no-ui-translate]';
  let isTranslating = false;

  function trimParts(value) {
    const leading = (value.match(/^\s*/) || [''])[0];
    const trailing = (value.match(/\s*$/) || [''])[0];
    const core = value.slice(leading.length, value.length - trailing.length).replace(/\s+/g, ' ');
    return { leading, core, trailing };
  }

  function translateCore(core) {
    if (!core || language === 'en') {
      return core;
    }
    if (Object.prototype.hasOwnProperty.call(catalog, core)) {
      return catalog[core];
    }
    let translated = core;
    for (const sourcePrefix of Object.keys(prefixCatalog)) {
      if (translated === sourcePrefix) {
        translated = prefixCatalog[sourcePrefix];
        break;
      }
      if (translated.startsWith(sourcePrefix + ' ')) {
        translated = prefixCatalog[sourcePrefix] + translated.slice(sourcePrefix.length);
        break;
      }
    }
    for (const sourceFragment of Object.keys(fragmentCatalog)) {
      if (translated.includes(sourceFragment)) {
        translated = translated.split(sourceFragment).join(fragmentCatalog[sourceFragment]);
      }
    }
    return translated;
  }

  function translateString(value) {
    if (!value || language === 'en') {
      return value;
    }
    const parts = trimParts(String(value));
    const translated = translateCore(parts.core);
    if (translated === parts.core) {
      return value;
    }
    return parts.leading + translated + parts.trailing;
  }

  function translateTextNode(node) {
    if (!node.nodeValue || !node.nodeValue.trim()) {
      return;
    }
    const parent = node.parentElement;
    if (!parent || parent.closest(skipSelector)) {
      return;
    }
    const translated = translateString(node.nodeValue);
    if (translated !== node.nodeValue) {
      node.nodeValue = translated;
    }
  }

  function translateAttributes(element) {
    if (!element || element.nodeType !== 1 || element.closest(skipSelector)) {
      return;
    }
    attributes.forEach(function (attribute) {
      if (!element.hasAttribute(attribute)) {
        return;
      }
      const value = element.getAttribute(attribute);
      const translated = translateString(value);
      if (translated !== value) {
        element.setAttribute(attribute, translated);
      }
    });
  }

  function translateTree(root) {
    if (language === 'en' || !root || isTranslating) {
      return;
    }
    isTranslating = true;
    try {
      if (root.nodeType === Node.TEXT_NODE) {
        translateTextNode(root);
      } else if (root.nodeType === Node.ELEMENT_NODE || root.nodeType === Node.DOCUMENT_NODE) {
        if (root.nodeType === Node.ELEMENT_NODE) {
          translateAttributes(root);
        }
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
          acceptNode: function (node) {
            const parent = node.parentElement;
            if (!node.nodeValue || !node.nodeValue.trim() || !parent || parent.closest(skipSelector)) {
              return NodeFilter.FILTER_REJECT;
            }
            return NodeFilter.FILTER_ACCEPT;
          }
        });
        const nodes = [];
        while (walker.nextNode()) {
          nodes.push(walker.currentNode);
        }
        nodes.forEach(translateTextNode);
        root.querySelectorAll && root.querySelectorAll('*').forEach(translateAttributes);
      }
      document.title = translateString(document.title);
    } finally {
      isTranslating = false;
    }
  }

  window.ModuLearnI18n = {
    language,
    catalogs,
    t: function (value) {
      return translateString(value);
    },
    translateTree
  };

  document.addEventListener('DOMContentLoaded', function () {
    translateTree(document.body);
    if (language === 'en' || !window.MutationObserver || !document.body) {
      return;
    }
    const observer = new MutationObserver(function (mutations) {
      if (isTranslating) {
        return;
      }
      mutations.forEach(function (mutation) {
        if (mutation.type === 'characterData') {
          translateTree(mutation.target);
        } else if (mutation.type === 'attributes') {
          translateAttributes(mutation.target);
        } else {
          mutation.addedNodes.forEach(translateTree);
        }
      });
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: attributes
    });
  });
})();
