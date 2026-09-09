obj-m += msi-ec.o
ccflags-y := -std=gnu11 -Wno-declaration-after-statement
KERNELRELEASE ?= $(shell uname -r)
all:
	$(MAKE) -C /lib/modules/$(KERNELRELEASE)/build M=$(CURDIR) modules
