idf_component_register(SRCS "desk_can.c" INCLUDE_DIRS "include" REQUIRES driver)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
