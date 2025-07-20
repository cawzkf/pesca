<!-- pescasync/
├── requirements.txt           # Dependências
├── .env                      # Variáveis de ambiente
├── .gitignore               # Ignorar arquivos
├── README.md                # Documentação
├── config/                  # Configurações
│   ├── __init__.py
│   ├── settings.py         # Configurações globais
│   └── database.py         # Config do banco
├── src/                    # Código fonte
│   ├── __init__.py
│   ├── domain/             # Regras de negócio (core)
│   │   ├── __init__.py
│   │   ├── entities/       # Entidades do domínio
│   │   ├── use_cases/      # Casos de uso
│   │   └── repositories/   # Interfaces dos repositórios
│   ├── infrastructure/     # Implementações técnicas
│   │   ├── __init__.py
│   │   ├── database/       # Acesso a dados
│   │   ├── sensors/        # Simuladores de sensores
│   │   └── ai/            # Algoritmos de IA
│   ├── presentation/       # Interface do usuário
│   │   ├── __init__.py
│   │   ├── dashboard/      # Dashboard Streamlit
│   │   └── components/     # Componentes reutilizáveis
│   └── shared/            # Código compartilhado
│       ├── __init__.py
│       ├── exceptions.py   # Exceções customizadas
│       └── utils.py       # Utilitários
├── tests/                 # Testes automatizados
│   ├── __init__.py
│   ├── unit/             # Testes unitários
│   ├── integration/      # Testes de integração
│   └── fixtures/         # Dados para testes
└── docs/                 # Documentação adicional -->


# PescaSync


Setup inicial completo - estrutura organizada seguindo Clean Architecture