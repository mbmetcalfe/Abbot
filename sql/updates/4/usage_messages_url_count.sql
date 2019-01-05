begin transaction;

alter table usage_messages add url_count integer default 1;
alter table usage_messages_archive add url_count integer default 1;

commit;