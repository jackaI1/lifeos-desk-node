idf_component_register(SRCS "desk_ess.c" INCLUDE_DIRS "include" REQUIRES desk_core)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
