# DataMapper Landing Page

Landing page para DataMapper, una aplicación asequible para mapear datos de base de datos origen a destino en migraciones de bases de datos.

## Estructura del Proyecto

```
landing/
├── src/
│   ├── components/
│   │   ├── splash.astro         # Hero section con animaciones
│   │   ├── features.astro       # Sección de características
│   │   ├── pricing.astro        # Planes de precios
│   │   ├── contact.astro        # Información de contacto
│   │   ├── header.astro         # Navegación principal
│   │   └── footer.astro         # Pie de página
│   ├── pages/
│   │   └── index.astro          # Página principal
│   └── styles/
│       └── index.css            # Estilos globales
└── astro.config.mjs             # Configuración de Astro
```

## Características de la Landing

### Hero Section (Splash)
- Título impactante sobre DataMapper
- Descripción breve del servicio
- Botones CTA para registro e inicio de sesión
- Animaciones visuales con iconos de bases de datos

### Sección de Características
6 características principales de DataMapper

### Sección de Precios
- Plan Gratuito: 0€/mes
- Plan Premium: 30€/mes

### Sección de Contacto
Email: datamapassistant@gmail.com

## Tecnologías

- Astro 5.x
- astro-icon
- micromodal
- Inter Variable Font

## Comandos

```bash
npm install     # Instalar dependencias
npm run dev     # Servidor desarrollo
npm run build   # Build producción
npm run preview # Preview del build
```

## Contacto

datamapassistant@gmail.com
