import os
import subprocess
import sys
import time
import pandas as pd

repo_path = os.getcwd()
databricks = False
print(f"Using fallback path: {repo_path}")
print("Not running in a Databricks environment")

from config import config
from ingestion.change_index import initialise_client, delete_record, embedd_df, upload_record
from src.table_helper import upload_df_to_all_tables, upload_df_to_table, retrieve_table_to_df, check_table_exists, create_table,delete_rows_in_table
from src.blob_helper import upload_file_data_to_blob
from process_data_for_index import create_whole_index_data, create_diff_index_data
from src.compare_differences import compare_data, compare_mapping_table
from src.create_delete_index import check_index_exist, delete_index, create_your_index_ENV
from src.generate_mapping_table import create_mapping_table, get_sharepoint_files
from src.combine_previous_current_chunk_tables import combine_tables
from get_terminologies_data import get_terminologies_to_blob

def ingestion_load(config):
    ##########################
    ### Set some Variables ###
    ##########################
    id_column_name = 'id' ## ideally to use index as default. for langchain, use id.
    index_name = config.INDEX_NAME
    logger = config.logger
    ENV=config.ENV
    ENV = os.environ.get("ENV")
    logger.info("Running in " + ENV + " ENV")
    cert_path = config.REQUESTS_CA_BUNDLE
    logger.info("CERT PATH :"+cert_path)
    embeddings_column_dict = {'content' : 'content_vector'} ## if langchain use this.
    ## embeddings_column_dict = {'question':'embeddingsQns', 'Question-Answer':'embeddingsQnsAns'}
    ## columns_to_drop = ['Question-Answer'] ## IF any to drop after embed.
    columns_to_drop = None
    logger.info(f"USE_APIM : {config.USE_APIM}")
    #################################################################################
    ### You can include a check in previous mapping table and mapping table here. ###
    #################################################################################
    mapping_table_name = config.MAPPING_TABLE_NAME
    folder_path = config.SHAREPOINT_FOLDER_NAME
    if check_table_exists(config.INDEX_TABLE_NAME, config):
        previous_index_data = retrieve_table_to_df(config.INDEX_TABLE_NAME, config)    
    else:
        logger.info("ChunkMappingTable does not exists.")
        previous_index_data = pd.DataFrame()

    data_to_update_index = pd.DataFrame()
    if check_table_exists(mapping_table_name, config):
        previous_mt_df = retrieve_table_to_df(mapping_table_name, config) 
        current_mt_df = create_mapping_table(folder_path, config)
        if current_mt_df.empty:
            logger.error("No files fetched from sharepoint! please check sharepoint folder path!")
            raise ValueError("No files fetched from sharepoint! please check sharepoint folder path!")
        if not previous_mt_df.empty:
            mapping_table_status_list = compare_mapping_table(previous_mt_df, current_mt_df)
            mapping_table_status = mapping_table_status_list[0]
            if mapping_table_status == 'no_change':
                logger.info(f"Mapping Table Status : {mapping_table_status}")
                logger.info("No change in Mapping Table. End function")
                return True
            elif mapping_table_status == 'changes':
                modified_df = mapping_table_status_list[1]
                delete_df = mapping_table_status_list[2]
                insert_df = mapping_table_status_list[3]
                
                change = {}
                
                if modified_df.empty:
                    modified_id_df = pd.DataFrame()
                else:
                    if not previous_index_data.empty:
                        modified_id_df = modified_df.merge(previous_index_data,on='Filename',how='left')
                        delete = list(modified_id_df[id_column_name])
                        change['delete'] = delete
                    else:
                        logger.error("Error with getting id for modified_df to delete. Scenario should not occur with existing previous mapping table but no previous index data.")
                        raise ValueError("Error with getting id for modified_df to delete. Scenario should not occur with existing previous mapping table but no previous index data.")
                    modified_id_df = create_diff_index_data(modified_df, config)
                    change['add'] = list(modified_id_df[id_column_name])

                delete = []
                if delete_df.empty:
                    delete_df = pd.DataFrame()
                else:
                    delete_df = delete_df.drop(columns=['PartitionKey','RowKey'])
                    delete_df = delete_df[['Filename']]
                    if not previous_index_data.empty:
                        delete_id_df = delete_df.merge(previous_index_data,on='Filename',how='left')
                        delete = list(delete_id_df[id_column_name])
                    else:
                        logger.error("Error with getting id for delete_df. Scenario should not occur with existing previous mapping table but no previous index data.")
                        raise ValueError("Error with getting id for delete_df. Scenario should not occur with existing previous mapping table but no previous index data.")
                    
                add = []
                if insert_df.empty:
                    insert_id_df = pd.DataFrame()
                else:
                    insert_id_df = create_diff_index_data(insert_df, config)
                    add = list(insert_id_df[id_column_name])
                data_to_update_index = pd.concat([modified_id_df,insert_id_df],ignore_index=True) ## Could be empty.
                action_to_be_taken = {"Action":"Update Index", "Change":change, "Delete":delete, "Add":add}
            else:
                logger.error("Error with mapping_table_status : Not classified")
                raise ValueError("Error with both previous and current mapping tables. please check!")
        else:
            previous_mt_df = retrieve_table_to_df(mapping_table_name, config) 
            current_mt_df = create_mapping_table(folder_path, config)
            if current_mt_df.empty:
                logger.error("No files fetched from sharepoint! please check sharepoint folder path!")
                raise ValueError("No files fetched from sharepoint! please check sharepoint folder path!")
            if not previous_mt_df.empty:
                mapping_table_status_list = compare_mapping_table(previous_mt_df, current_mt_df)
                mapping_table_status = mapping_table_status_list[0]
                if mapping_table_status == 'no_change':
                    logger.info(f"Mapping Table Status : {mapping_table_status}")
                    logger.info("No change in Mapping Table. End function")
                    return True
                elif mapping_table_status == 'changes':
                    modified_df = mapping_table_status_list[1]
                    delete_df = mapping_table_status_list[2]
                    insert_df = mapping_table_status_list[3]

                    change = {}
                    modified_id_df = pd.DataFrame()
                    if modified_df.empty:
                        modified_id_df = pd.DataFrame()
                    else:
                        if not previous_index_data.empty:
                            modified_id_df = modified_df.merge(previous_index_data,on='Filename',how='left')
                            delete = list(modified_id_df[id_column_name])
                            change['delete'] = delete
                        else:
                            logger.error("Error with getting id for modified_df to delete. Scenario should not occur with existing previous mapping table but no previous index data.")
                            raise ValueError("Error with getting id for modified_df to delete. Scenario should not occur with existing previous mapping table but no previous index data.")
                        modified_id_df = create_diff_index_data(modified_df)
                        change['add'] = list(modified_id_df[id_column_name])

                    delete = []
                    if delete_df.empty:
                        delete_df = pd.DataFrame()
                    else:
                        delete_df = delete_df.drop(columns=['PartitionKey','RowKey'])
                        delete_df = delete_df[['Filename']]
                        if not previous_index_data.empty:
                            delete_id_df = delete_df.merge(previous_index_data,on='Filename',how='left')
                            delete = list(delete_id_df[id_column_name])
                        else:
                            logger.error("Error with getting id for delete_df. Scenario should not occur with existing previous mapping table but no previous index data.")
                            raise ValueError("Error with getting id for delete_df. Scenario should not occur with existing previous mapping table but no previous index data.")
                        
                    add = []
                    insert_id_df = pd.DataFrame()
                    if insert_df.empty:
                        insert_df = pd.DataFrame()
                    else:
                        insert_id_df = create_diff_index_data(insert_df)
                        add = list(insert_id_df[id_column_name])
                    
                    
                    data_to_update_index = pd.concat([modified_id_df,insert_id_df],ignore_index=True) ## Could be empty.
                    action_to_be_taken = {"Action":"Update Index", "Change":change, "Delete":delete, "Add":add}
                else:
                    logger.error("Error with mapping_table_status : Not classified")
                    raise ValueError("Error with both previous and current mapping tables. please check!")
            else:
                ## Empty data_to_update_index
                current_mt_df['PartitionKey'] = 'partition1'
                current_mt_df['RowKey'] = ['row' + str(i) for i in range(len(current_mt_df))]
                # upload_df_to_all_tables(mapping_table_name, current_mt_df, config)      
                logger.info("New mapping table added into ATS. Continue to generate the whole index.")
                action_to_be_taken = {"Action":"Delete Index"}
    else:
        ## Empty data_to_update_index
        create_table(mapping_table_name, config)
        current_mt_df = create_mapping_table(folder_path, config)   
        logger.info("New mapping table added into ATS. Continue to generate the whole index.")
        action_to_be_taken = {"Action":"Delete Index"}
    logger.info(action_to_be_taken)
    
    ##################
    ### Data Check ###
    ##################
    index_action = action_to_be_taken.get('Action')
    if data_to_update_index.empty:
        if index_action == 'Delete Index':
            ## Generate current round index data    
            logger.info("Generating the full current_index_data")
            current_index_data = create_whole_index_data(current_mt_df, config)
            # current_index_data.to_excel("current_index_data.xlsx",index=False)
            ########################################################
            ### Compare data to identify differences in content. ###
            ########################################################

            if previous_index_data.empty:
                logger.info("No data from Previous Round ATS")
                if current_index_data.empty:
                    logger.error("Error with processing data. Pls check!")
                    raise ValueError("Error with processing data. Pls check!")
                else:
                    logger.info("Upload all data in current_index_data")
                    ## Upload all the data in the current_index_data
                    action_to_be_taken = {"Action":"Delete Index"}
            else:
                previous_index_data = previous_index_data.drop(columns=['PartitionKey','RowKey'])
                if current_index_data.empty:
                    logger.error("Error with processing data. Pls check!")
                    raise ValueError("Error with processing data. Pls check!")
                else:
                    logger.info("Check for differences")
                    ## Remember to change your id_column_name
                    action_to_be_taken = compare_data(previous_index_data, current_index_data,id_column_name=id_column_name)
        else:
            if action_to_be_taken:
                current_index_data = data_to_update_index
            else:
                logger.error("No action determined. Throw Error!")
                raise ValueError("No action determined. Throw Error!")   
    else:
        if action_to_be_taken:
            current_index_data = data_to_update_index
        else:
            logger.error("No action determined. Throw Error!")
            raise ValueError("No action determined. Throw Error!")
        
    ####################
    ### Update Index ###
    ####################

    ## Check if index exists. If does not exist, will create a new index. Else will utilise existing index.
    index_action = action_to_be_taken.get('Action')
    azure_client_dict = initialise_client(config=config)
    if index_action == 'Delete Index':
        ## Check if index exists.
        if check_index_exist(index_name, api_version=config.SEARCH_INDEX_API_VERSION, config=config):
            if delete_index(index_name, api_version=config.SEARCH_INDEX_API_VERSION, config=config):
                ## Index deleted. Time to upload all the rows in current_index_data.
                ## Need to add sleep to let microsoft delete index.
                logger.info("Time Sleep to prevent recreating index too fast and causing an error.")
                time.sleep(5)
        ## Create Index
        if create_your_index_ENV(config=config)==False:
            logger.error("Error creating Index")
            raise ValueError("Error creating Index")
        for index in list(current_index_data[id_column_name]):
            '''Get record'''
            record_df = current_index_data[current_index_data[id_column_name]==index]
            '''Embed Query'''
            ## if langchain:
            embeddings_column_dict = {'content' : 'content_vector'}
            ## embeddings_column_dict = {'question':'embeddingsQns', 'Question-Answer':'embeddingsQnsAns'}
            ##columns_to_drop = ['Question-Answer'] ## IF any to drop after embed.
            record_df = embedd_df(record_df, embeddings_column_dict, columns_to_drop, config=config)
            '''Upload'''
            upload_record(record_df, id_column_name, azure_client_dict, config=config)
    elif index_action == "Update Index":
        ## {"Action":"Update Index", "Change":differences, "Delete":delete_rows, "Add":added_rows}
        ## Change = Delete, and Upload.
        differences = action_to_be_taken['Change']
        for index in differences.get('delete',[]):
            '''Delete'''
            delete_record(index, id_column_name, azure_client_dict, config=config)
        for index in differences.get('add',[]):
            '''Get record'''
            record_df = current_index_data[current_index_data[id_column_name]==index]
            '''Embed Query'''
            record_df = embedd_df(record_df, embeddings_column_dict, columns_to_drop, config=config)
            '''Upload'''
            upload_record(record_df, id_column_name, azure_client_dict, config=config)
        ## Delete = Delete only.
        to_delete = action_to_be_taken['Delete']
        for index in to_delete:
            '''Delete'''
            delete_record(index, id_column_name, azure_client_dict, config=config)
        ## Add = Upload Only.
        add = action_to_be_taken['Add']
        for index in add:
            '''Get record'''
            record_df = current_index_data[current_index_data[id_column_name]==index]
            '''Embed Query'''
            ## if langchain:
            ## embeddings_column_dict = {'content' : 'content_vector}
            embeddings_column_dict = {'content':'content_vector'}
            record_df = embedd_df(record_df, embeddings_column_dict, columns_to_drop, config=config)
            '''Upload'''
            upload_record(record_df, id_column_name, azure_client_dict, config=config)
    elif index_action == "No Action":
        logger.info("No differences in content. No need to re-upload into ATS.")
        return True
    elif index_action == "Error":
        logger.info("Error with comparison. Do not continue")
        return False

    ###################################################
    ### Overwrite current round index data into ATS ###
    ###################################################
    current_mt_df['PartitionKey'] = 'partition1'
    current_mt_df['RowKey'] = ['row' + str(i) for i in range(len(current_mt_df))]
    upload_df_to_all_tables(mapping_table_name, current_mt_df, config)
    # current_mt_df.to_csv("current_mapping_table.csv",index=False)

    # current_index_data.to_excel("current_index_data.xlsx",index=False)
    final_current_index_data = combine_tables(previous_index_data, current_index_data, action_to_be_taken, id_column_name)
    final_current_index_data["PartitionKey"] = ["partition1" for i in range(final_current_index_data.shape[0])]
    final_current_index_data["RowKey"] = ["row"+str(i) for i in range(final_current_index_data.shape[0])]
    if columns_to_drop:
        final_current_index_data = final_current_index_data.drop(columns_to_drop, axis=1)
    upload_df_to_all_tables(config.INDEX_TABLE_NAME, final_current_index_data, config=config)
    # final_current_index_data.to_excel('final_current_index_data.xlsx',index=False)
    return True

if __name__ == "__main__":
    try:
        config = Config(repo_path=repo_path, databricks=databricks)
        logger = config.logger
        if ingestion_load(config):
            logger.info("Updating of Genie AI cli data protection completed.")
            config.upload_log_to_blob()
            logger.info("Updating of Genie AI Group Compliance Terminologies completed.")
        else:
            logger.error("Error with Data Ingestion for Genie AI CLI data protection. Please check your scripts.")
            config.upload_log_to_blob()

    except Exception as e:
        logger.error("Error with Data Ingestion ",e)
        config.upload_log_to_blob()
