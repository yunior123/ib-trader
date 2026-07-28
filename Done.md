
- [x] **hecho `cef86ca`** (`live.html:2107-2114`). La causa: cuando el feed paraba, `rem` se volvia negativo, se topaba a 0 y el '00:00' se congelaba. Ahora si el feed muere (rem < -sec) el timer DESAPARECE; con datos vivos (overnight/Corea) cuenta normal. Verificado en codigo.
      *(era)* **[pendiente — mismo bug del RTH 930] "the blue timer for the bars stops at 15:30"**
