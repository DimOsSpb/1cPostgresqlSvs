# Purpose of work

    Build a ceph cluster, connect to the host,
    perform operations with pictures on the created ceph.

    1. Set replication factor 3
    3. The quorum must be from 2 to 4 nodes upon request 
    4. MDS must be running on 2 nodes, 1 and 3 nodes in standby status
    5. The cluster should consist of 3 pools
    6. NVMe otimization
    7. Configure the firewall so that access to the cluster is only possible with
    specific hosts except ssh port
    8. After assembling the cluster, you need to connect it to the host, show
    health status via UI
    9. In ceph mnt point on host create two folders: pic and pic_links
    10. In the pic folder, upload pictures from the remote host 
    11. In the pic_links folder, use a script to create a structure of 20 folders and
    make links to each image file from the folder in equal shares, all
    links must be unique and match the number of images
    from the pic folder 
    12. Conduct stress testing of the created cluster


## 1. Build a ceph cluster of 3 nodes + a controller

### Initial data

    - Prepared nodes (system installed (debian), networks configured ...):
        - 3 nodes for OSD:
            ceph1 192.168.0.61,10.10.10.11
            ceph2 192.168.0.62,10.10.10.12
            ceph3 192.168.0.63,10.10.10.13
        - 1 node
            ceph0 192.168.0.60,10.10.10.10

    - For standard maintenance and configuration management we will deploy and manage Ceph cluster using Ansible

### Key authentication (for Ansible)

    On admih host:

    - add ceph(0-3) on /etsc/hosts:

    ssh-keygen -t ed25519
    ssh-copy-id -i ~/.ssh/id_ed25519.pub root@ceph0
    ssh-copy-id -i ~/.ssh/id_ed25519.pub root@ceph1
    ssh-copy-id -i ~/.ssh/id_ed25519.pub root@ceph2
    ssh-copy-id -i ~/.ssh/id_ed25519.pub root@ceph3

### Ansible

    git clone https://github.com/ceph/ceph-ansible.git

    cd ceph-ansible

    git checkout stable-6.0

    pip install -r requirements.txt

    - add installed packages /bin in PATH
	
    cp site.yml.sample site.yml
    cp group_vars/all.yml.sample group_vars/all.yml
    cp group_vars/mons.yml.sample group_vars/mons.yml
    cp group_vars/osds.yml.sample group_vars/osds.yml    

### Create inventory file, playbook and configuration for Ceph cluste



# Links to information sources
  * [Ceph documentation](https://docs.ceph.com/en/pacific/)
  * [ceph-ansible](https://docs.ceph.com/projects/ceph-ansible/en/latest/glossary.html)